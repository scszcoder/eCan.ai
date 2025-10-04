from datetime import datetime
import time


class VEHICLE:
    def __init__(self, parent, name="x", ip="0.0.0.0"):
        self.parent = parent
        self.bot_ids = []
        self.arch = ""
        self.os = parent.os_short if parent else "unknown"
        self.name = name
        self.ip = ip
        self.id = ""
        self.status = "offline"
        self.last_update_time = datetime.strptime("1900-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
        self.mstats = []
        self.field_link = None
        self.daily_mids = []
        self.functions = ""
        self.CAP = 16*4*2       # 16xhr/day, 4x15min time slot/hr, 1 agent can run every 2 days.
        self.test_disabled = False
        
        # Performance and device information fields
        self.battery = 100  # Battery percentage (default 100% for non-mobile devices)
        self.location = "Local"  # Device location
        self.last_maintenance = None  # Last maintenance time
        self.total_distance = 0  # Total distance (0 for non-mobile devices)
        self.current_task = ""  # Current task
        self.next_maintenance = None  # Next maintenance time
        self.type = "Computer"  # Device type
        
        # System performance metrics
        self.cpu_usage = 0.0  # CPU usage percentage
        self.memory_usage = 0.0  # Memory usage percentage
        self.disk_usage = 0.0  # Disk usage percentage
        self.network_status = "connected"  # Network status
        self.uptime = 0  # Uptime in seconds

    def getFieldLink(self):
        return self.field_link

    def setFieldLink(self, fl):
        self.field_link = fl

    def getVid(self):
        return self.id

    def setVid(self, vid):
        self.id = vid

    def getStatus(self):
        return self.status

    def setStatus(self, stat):
        self.status = stat
        self.last_update_time = datetime.now()

    def getLastUpdateTime(self):
        return self.last_update_time

    def setMStats(self, mstats):
        self.mstats = mstats

    def getMStats(self):
        return self.mstats

    def getIP(self):
        return self.ip

    def setIP(self, ip):
        self.ip = ip

    def getName(self):
        return self.name

    def setName(self, name):
        self.name = name

    def getArch(self):
        return self.arch

    def setArch(self, arch):
        self.arch = arch

    def getOS(self):
        return self.os

    def setOS(self, vos):
        self.os = vos

    def getBotIds(self):
        return self.bot_ids

    def addBot(self, bid):
        if len(self.getBotIds()) < self.CAP and bid not in self.getBotIds():
            self.bot_ids.append(bid)
            nAdded = 1
        else:
            nAdded = 0

        return nAdded

    def removeBot(self, bid):
        if bid in self.bot_ids:
            self.bot_ids.remove(bid)
            nRemoved = 1
        else:
            nRemoved = 0

        return nRemoved


    def setBotIds(self, bot_ids):
        self.bot_ids = bot_ids

    def getBotsOverCapStatus(self):
        return (len(self.bot_ids) > self.CAP)

    def getMids(self):
        return self.daily_mids

    def setMids(self, mids):
        self.daily_mids = mids

    def getFunctions(self):
        return self.functions

    def setFunctions(self, fs):
        self.functions = fs

    def getTestDisabled(self):
        return self.test_disabled

    def setTestDisabled(self, td):
        self.test_disabled = td
    
    # 新增字段的 getter/setter 方法
    def getBattery(self):
        return self.battery
    
    def setBattery(self, battery):
        self.battery = max(0, min(100, battery))  # 限制在0-100之间
    
    def getLocation(self):
        return self.location
    
    def setLocation(self, location):
        self.location = location
    
    def getLastMaintenance(self):
        return self.last_maintenance
    
    def setLastMaintenance(self, last_maintenance):
        self.last_maintenance = last_maintenance
    
    def getTotalDistance(self):
        return self.total_distance
    
    def setTotalDistance(self, total_distance):
        self.total_distance = max(0, total_distance)
    
    def getCurrentTask(self):
        return self.current_task
    
    def setCurrentTask(self, current_task):
        self.current_task = current_task
    
    def getNextMaintenance(self):
        return self.next_maintenance
    
    def setNextMaintenance(self, next_maintenance):
        self.next_maintenance = next_maintenance
    
    def getType(self):
        return self.type
    
    def setType(self, vehicle_type):
        self.type = vehicle_type
    
    def getCpuUsage(self):
        return self.cpu_usage
    
    def setCpuUsage(self, cpu_usage):
        self.cpu_usage = max(0, min(100, cpu_usage))
    
    def getMemoryUsage(self):
        return self.memory_usage
    
    def setMemoryUsage(self, memory_usage):
        self.memory_usage = max(0, min(100, memory_usage))
    
    def getDiskUsage(self):
        return self.disk_usage
    
    def setDiskUsage(self, disk_usage):
        self.disk_usage = max(0, min(100, disk_usage))
    
    def getNetworkStatus(self):
        return self.network_status
    
    def setNetworkStatus(self, network_status):
        self.network_status = network_status
    
    def getUptime(self):
        return self.uptime
    
    def setUptime(self, uptime):
        self.uptime = max(0, uptime)

    def genJson(self):
        jsd = {
                "vid": self.id,
                "ip": self.ip,
                "name": self.name,
                "os": self.os,
                "arch": self.arch,
                "bot_ids": self.bot_ids,
                "status": self.status,
                "functions": self.functions,
                "test_disabled": self.test_disabled,
                "last_update_time": self.last_update_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:23],
                # 新增字段
                "battery": self.battery,
                "location": self.location,
                "lastMaintenance": self.last_maintenance,
                "totalDistance": self.total_distance,
                "currentTask": self.current_task,
                "nextMaintenance": self.next_maintenance,
                "type": self.type,
                "cpuUsage": self.cpu_usage,
                "memoryUsage": self.memory_usage,
                "diskUsage": self.disk_usage,
                "networkStatus": self.network_status,
                "uptime": self.uptime,
                # 原有字段
                "CAP": self.CAP,
                "mstats": self.mstats,
                "field_link": self.field_link,
                "daily_mids": self.daily_mids
                }
        return jsd

    def to_dict(self):
        """返回车辆对象的字典表示，兼容原有genJson结构。"""
        return self.genJson()

    def loadJson(self, dj):
        self.id = dj.get("vid", -1)
        self.ip = dj.get("ip", "")
        self.setName(dj.get("name", ""))
        self.os = dj.get("os", "")
        self.arch = dj.get("arch", "")  # Default to empty string if "arch" is missing
        self.setStatus(dj.get("status", ""))
        self.bot_ids = dj.get("bot_ids", [])
        self.functions = dj.get("functions", "")
        self.test_disabled = dj.get("test_disabled", False)
        self.last_update_time = datetime.strptime(dj.get("last_update_time", "1970-01-01 00:00:00.000"), "%Y-%m-%d %H:%M:%S.%f")
        
        # 加载新增字段
        self.battery = dj.get("battery", 100)
        self.location = dj.get("location", "Local")
        self.last_maintenance = dj.get("lastMaintenance", None)
        self.total_distance = dj.get("totalDistance", 0)
        self.current_task = dj.get("currentTask", "")
        self.next_maintenance = dj.get("nextMaintenance", None)
        self.type = dj.get("type", "Computer")
        self.cpu_usage = dj.get("cpuUsage", 0.0)
        self.memory_usage = dj.get("memoryUsage", 0.0)
        self.disk_usage = dj.get("diskUsage", 0.0)
        self.network_status = dj.get("networkStatus", "connected")
        self.uptime = dj.get("uptime", 0)
        
        # 加载原有扩展字段
        self.CAP = dj.get("CAP", 16*4*2)
        self.mstats = dj.get("mstats", [])
        self.field_link = dj.get("field_link", None)
        self.daily_mids = dj.get("daily_mids", [])
    
    def updateSystemMetrics(self):
        """更新系统性能指标"""
        try:
            import psutil
            
            # 更新CPU使用率
            self.cpu_usage = psutil.cpu_percent(interval=0.1)
            
            # 更新内存使用率
            memory = psutil.virtual_memory()
            self.memory_usage = memory.percent
            
            # 更新磁盘使用率
            disk = psutil.disk_usage('/')
            self.disk_usage = (disk.used / disk.total) * 100
            
            # 更新网络状态 (简化检查)
            try:
                import socket
                socket.create_connection(("8.8.8.8", 53), timeout=3)
                self.network_status = "connected"
            except:
                self.network_status = "disconnected"
            
            # 更新运行时间
            self.uptime = int(time.time() - psutil.boot_time())
            
            # 更新最后更新时间
            self.last_update_time = datetime.now()
            
        except ImportError:
            # 如果没有psutil，使用默认值
            pass
        except Exception as e:
            # 处理其他异常
            print(f"Error updating system metrics: {e}")
    
    def getSystemInfo(self):
        """获取完整的系统信息字典"""
        self.updateSystemMetrics()
        return {
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "disk_usage": self.disk_usage,
            "network_status": self.network_status,
            "uptime": self.uptime,
            "battery": self.battery,
            "location": self.location,
            "type": self.type
        }
