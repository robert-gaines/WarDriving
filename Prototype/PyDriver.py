#!/usr/bin/env python3

from concurrent.futures import thread

try:
    from scapy.arch.windows import get_windows_if_list
    import serial.tools.list_ports
    from PyQt5.QtWidgets import *
    from PyQt5.QtCore import *
    from PyQt5.QtGui import *
    from scapy.all import *
    import subprocess
    import xlsxwriter
    import pynmea2
    import time
    import csv
    import sys
    import os
except Exception as e:
    sys.exit(1)

class Worker(QObject):        

    rx_gps_fix            = pyqtSignal(dict)
    located_access_point  = pyqtSignal(list)
    finished              = pyqtSignal()

    def __init__(self,com_port,baud_rate,mon_int):
        super().__init__()
        self.SessionValid      = True
        self.monitor_interface = mon_int
        self.gps_com_port      = com_port
        self.baud_rate         = baud_rate
        self.bssid_list        = []
        self.new_ap_entry      = []
        self.log_file   = self.GenerateFileName()
        self.log_obj    = open(self.log_file,'w')
        self.log_obj.write('ESSID,BSSID,LATITUDE DIRECTION,LATITUDE,LONGITUDE DIRECTION,LONGITUDE,ALTITUDE,ALTITUDE UNIT,GPS FIX QUALITY\n')

    def GenerateFileName(self):    
        n  = datetime.now()
        t  = n.strftime("%m:%d:%Y - %H:%M:%S")
        ts = n.strftime("%m_%d_%Y_%H_%M_%S")
        log_file = "Session_"+ts+'.csv'
        return log_file

    def Parser(self,pkt):
        try:
            if(pkt.haslayer(Dot11)):
                if(pkt.type== 0 and pkt.subtype == 8):
                    if(pkt.info == b''):
                        essid = 'Unknown'
                    elif(len(pkt.info.hex()) > 48):
                        essid = 'Unknown'
                    else:
                        essid = str(pkt.info,'utf-8')
                    if(pkt.addr2 not in self.bssid_list):
                        ap_geo_fix = self.GetGeoFix(self.gps_com_port,self.baud_rate)
                        if((essid == '') or ('NULL' in essid )):
                            essid = 'Unknown'
                        latitude   = str(ap_geo_fix['lat_direction'])+' '+str(ap_geo_fix['latitude'])
                        longitude  = str(ap_geo_fix['lon_direction'])+' '+str(ap_geo_fix['longitude'])
                        altitude   = str(ap_geo_fix['height'])+' '+str(ap_geo_fix['height_unit'])
                        fix_qual   = str(ap_geo_fix['quality'])
                        bssid      = pkt.addr2
                        self.bssid_list.append(bssid)
                        self.new_ap_entry = [essid,bssid,latitude,longitude,altitude,fix_qual]
                        log_entry = "%s,%s,%s,%s,%s,%s,%s,%s,%s\n" % (essid,bssid,str(ap_geo_fix['lat_direction']),latitude,str(ap_geo_fix['lon_direction']),longitude,altitude,str(ap_geo_fix['height_unit']),fix_qual)
                        self.log_obj.write(log_entry)
                        self.located_access_point.emit(self.new_ap_entry)
        except:
            pass
        finally:
            return

    def GetGeoFix(self,port,rate):
        gps_fix = {}
        try:
            serial_instance = serial.Serial()
            serial_instance.baudrate = rate
            serial_instance.port = port
            serial_instance.open()
            fix_data = serial_instance.readline().decode('ascii',errors='replace')
            fix_data = fix_data.strip()
            if('GP' in fix_data):
                parsed_fix = pynmea2.parse(fix_data)
                latitude   = parsed_fix.latitude
                latitude   = round(latitude,2)
                longitude  = parsed_fix.longitude
                longitude  = round(longitude,2)
                lat_dir    = parsed_fix.lat_dir
                lon_dir    = parsed_fix.lon_dir
                altitude   = parsed_fix.altitude
                alt_unit   = parsed_fix.altitude_units
                quality    = parsed_fix.gps_qual
                #
                gps_fix['latitude']      = latitude
                gps_fix['longitude']     = longitude
                gps_fix['lat_direction'] = lat_dir
                gps_fix['lon_direction'] = lon_dir
                gps_fix['height']        = altitude
                gps_fix['height_unit']   = alt_unit
                gps_fix['quality']       = quality
                #
                return gps_fix
                #
            else:
                return None
            serial_instance.close()
        except:
            return None

    def RunSession(self):
        while(self.SessionValid):
            self.current_gps_fix = self.GetGeoFix(self.gps_com_port,self.baud_rate)
            sniff(filter="",store=False,count=64,iface=r'%s'%self.monitor_interface,prn=self.Parser,monitor=True)
            if(self.current_gps_fix):
                self.rx_gps_fix.emit(self.current_gps_fix)
            time.sleep(1)
        self.finished.emit()

    def TerminateSession(self):
        self.SessionValid = False
        self.log_obj.close() 

class Window(QWidget):

    terminate_session = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.identified_access_points = []
        self.bssid_list               = []
        self.UI()

    def UI(self,parent=None):
        #
        super().__init__(parent)
        #
        QMainWindow.__init__(self)
        QTableWidget.__init__(self)
        QWidget.__init__(self)
        QLabel.__init__(self)
        #
        self.setWindowTitle('Python War Driver')
        self.setGeometry(350,200,1000,800)
        #
        #self.setStyleSheet("background-color: darkgray; border: 2px black solid")
        #
        self.com_port_label           = QLabel("COM Port for the GPS Antenna")
        self.com_port_combo_box       = QComboBox()
        self.com_ports                = self.ListPorts()
        for port in self.com_ports:
            self.com_port_combo_box.addItem(str(port))
        self.baud_rate_label          = QLabel("Baud Rate for the Serial Connection")
        self.baud_rate                = QLineEdit()
        #
        self.mon_int_label            = QLabel("Monitoring Wireless Interface")
        self.mon_int_combo_box        = QComboBox()
        self.net_ifaces               = self.GetInterfaces()
        for interface in self.net_ifaces:
            self.mon_int_combo_box.addItem(interface['name'])
        #
        self.start_button = QPushButton("Start Session",self)
        self.stop_button  = QPushButton("Stop Session", self)
        self.conf_button  = QPushButton("Set Parameters",self)
        self.reset_button = QPushButton("Reset Session", self)
        #
        self.current_latitude_label    = QLabel("Current Latitude")
        self.current_latitude          = QLineEdit() 
        self.current_longitude_label   = QLabel("Current Longitude")
        self.current_longitude         = QLineEdit()
        self.current_elevation_label   = QLabel("Elevation")
        self.current_elevation         = QLineEdit()
        self.current_fix_quality_label = QLabel("GPS Fix Quality")
        self.current_fix_quality       = QLineEdit()
        #
        self.tableWidgetLabel = QLabel("Identified Wireless Access Points")
        self.tableWidget      = QTableWidget()
        #self.tableWidget.setGeometry(100,100,100,100)
        self.tableWidget.verticalHeader().setVisible(False)
        self.tableWidget.horizontalHeader().setVisible(False)
        self.tableWidget.horizontalHeader().setStretchLastSection(True)
        self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tableWidget.setColumnCount(6)
        self.tableWidget.setRowCount(1)
        self.tableWidget.setItem(0,0,QTableWidgetItem("ESSID"))
        self.tableWidget.setItem(0,1,QTableWidgetItem("BSSID"))
        self.tableWidget.setItem(0,2,QTableWidgetItem("LATITUDE"))
        self.tableWidget.setItem(0,3,QTableWidgetItem("LONGITUDE"))
        self.tableWidget.setItem(0,4,QTableWidgetItem("ELEVATION"))
        self.tableWidget.setItem(0,5,QTableWidgetItem("GPS FIX QUALITY"))
        #
        main_layout               = QFormLayout()
        self.com_config_container = QVBoxLayout()
        self.int_config_container = QVBoxLayout()
        self.control_container    = QHBoxLayout()
        self.position_container   = QHBoxLayout()
        self.position_ctr_sub     = QHBoxLayout()
        self.status_container     = QHBoxLayout()
        self.display_container    = QVBoxLayout()
        #
        self.com_config_container.addWidget(self.com_port_label)
        self.com_config_container.addWidget(self.com_port_combo_box)
        self.com_config_container.addWidget(self.baud_rate_label)
        self.com_config_container.addWidget(self.baud_rate)
        self.int_config_container.addWidget(self.mon_int_label)
        self.int_config_container.addWidget(self.mon_int_combo_box)
        self.control_container.addWidget(self.conf_button)
        self.control_container.addWidget(self.start_button)
        self.control_container.addWidget(self.reset_button)
        self.control_container.addWidget(self.stop_button)
        self.position_container.addWidget(self.current_latitude_label)
        self.position_container.addWidget(self.current_latitude)
        self.position_container.addWidget(self.current_longitude_label)
        self.position_container.addWidget(self.current_longitude)
        self.position_ctr_sub.addWidget(self.current_elevation_label)
        self.position_ctr_sub.addWidget(self.current_elevation)
        self.position_ctr_sub.addWidget(self.current_fix_quality_label)
        self.position_ctr_sub.addWidget(self.current_fix_quality)
        self.display_container.addWidget(self.tableWidgetLabel)
        self.display_container.addWidget(self.tableWidget)
        main_layout.addRow(self.com_config_container)
        main_layout.addRow(self.int_config_container)
        main_layout.addRow(self.control_container)
        main_layout.addRow(self.position_container)
        main_layout.addRow(self.position_ctr_sub)
        main_layout.addRow(self.status_container)
        main_layout.addRow(self.display_container)
        #
        self.conf_button.clicked.connect(self.InitializeSession)
        self.reset_button.clicked.connect(self.ResetSession)
        #
        self.setLayout(main_layout)

    def InitializeSession(self):
        #
        gps_com_port  = self.com_port_combo_box.currentText() 
        gps_com_port  = gps_com_port.split('-')[0] 
        ant_baud_rate = self.baud_rate.text() 
        ws_mon_int    = self.mon_int_combo_box.currentText()
        #
        self.thread          = QThread(parent=self)
        self.MainWorker      = Worker(gps_com_port,ant_baud_rate,ws_mon_int)
        self.terminate_session.connect(self.MainWorker.TerminateSession)   
        self.MainWorker.moveToThread(self.thread)

        self.MainWorker.rx_gps_fix.connect(lambda: self.SetPresentPosition(self.MainWorker.current_gps_fix))
        self.MainWorker.located_access_point.connect(lambda: self.AddAccessPointTableEntry(self.MainWorker.new_ap_entry))

        self.MainWorker.finished.connect(self.thread.quit) 
        self.MainWorker.finished.connect(self.thread.deleteLater)  
        self.thread.finished.connect(self.thread.deleteLater)  

        self.thread.started.connect(self.MainWorker.RunSession)
        self.thread.finished.connect(self.MainWorker.TerminateSession)

        self.start_button.clicked.connect(self.thread.start)
        self.stop_button.clicked.connect(self.StopSession)
        self.reset_button.clicked.connect(self.ResetSession)

    def SetPresentPosition(self,gps_fix):
        latitude_raw  = str(gps_fix['latitude'])
        lat_direction = str(gps_fix['lat_direction'])
        latitude      = lat_direction+' '+latitude_raw 
        longitude_raw = str(gps_fix['longitude'])
        lon_direction = str(gps_fix['lon_direction'])
        longitude     = lon_direction+' '+longitude_raw
        altitude      = str(gps_fix['height'])
        alt_unit      = str(gps_fix['height_unit'])
        alt_str       = altitude+' '+alt_unit
        fix_quality   =  str(gps_fix['quality'])
        self.current_latitude.setText(latitude) 
        self.current_longitude.setText(longitude)
        self.current_elevation.setText(alt_str)
        self.current_fix_quality.setText(fix_quality)

    def AddAccessPointTableEntry(self,ap_entry):
        essid = ap_entry[0]
        bssid = ap_entry[1]
        latitude = ap_entry[2]
        longitude = ap_entry[3]
        elevation = ap_entry[4]
        fix_quality = ap_entry[5]
        current_row = self.tableWidget.rowCount()
        self.tableWidget.setRowCount(current_row+1)
        col_index   = 0
        cell_value  = QTableWidgetItem(essid)
        #cell_value.setForeground(QBrush(QColor(0, 255, 0)))
        self.tableWidget.setItem(current_row,col_index,cell_value) 
        col_index   = 1
        cell_value  = QTableWidgetItem(bssid)
        #cell_value.setForeground(QBrush(QColor(0, 255, 0)))
        self.tableWidget.setItem(current_row,col_index,cell_value)
        col_index   = 2
        cell_value  = QTableWidgetItem(latitude)
        #cell_value.setForeground(QBrush(QColor(0, 255, 0)))
        self.tableWidget.setItem(current_row,col_index,cell_value)
        col_index   = 3
        cell_value  = QTableWidgetItem(longitude)
        #cell_value.setForeground(QBrush(QColor(0, 255, 0)))
        self.tableWidget.setItem(current_row,col_index,cell_value)
        col_index   = 4
        cell_value  = QTableWidgetItem(elevation)
        #cell_value.setForeground(QBrush(QColor(0, 255, 0)))
        self.tableWidget.setItem(current_row,col_index,cell_value)
        col_index   = 5
        cell_value  = QTableWidgetItem(fix_quality)
        #cell_value.setForeground(QBrush(QColor(0, 255, 0)))
        self.tableWidget.setItem(current_row,col_index,cell_value)
        self.tableWidget.update()
        return

    def ResetSession(self):
        self.baud_rate.setText('')
        self.current_latitude.setText('')
        self.current_longitude.setText('')
        self.current_elevation.setText('')
        self.current_fix_quality.setText('')
        for row in range(self.tableWidget.rowCount()-1):
            try:
                self.tableWidget.removeRow(self.tableWidget.rowCount()-1)
                self.tableWidget.update()
            except:
                sys.exit(1)

    def ListPorts(self):
        ports = serial.tools.list_ports.comports()
        return ports

    def GetInterfaces(self):
        interfaces = get_windows_if_list()
        return interfaces

    def StopSession(self):
        #
        self.thread.quit()
        self.terminate_session.emit()

if(__name__ == '__main__'):
    app = QApplication(sys.argv)
    screen = Window()
    screen.show()
    sys.exit(app.exec_())
