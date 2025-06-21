from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget, QMessageBox)
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtCore import QTimer
import sys
import os
import random
from datetime import datetime
from gui.LoginoutGUI import Login
from gui.ipc.api import IPCAPI

# 配置日志以抑制 macOS IMK 警告
if sys.platform == 'darwin':
    os.environ["QT_LOGGING_RULES"] = "qt.webengine* = false"

from config.app_settings import app_settings
from config.app_info import app_info
from utils.logger_helper import logger_helper
from gui.core.web_engine_view import WebEngineView
from gui.core.dev_tools_manager import DevToolsManager
import uuid
from agent.chats.chat_service import ChatService

class WebGUI(QMainWindow):
    def __init__(self, py_login: Login=None):
        super().__init__()
        self.setWindowTitle("ECBot Agent")
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建中心部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        self.py_login: Login = py_login
        # 创建 Web 引擎
        self.web_engine_view = WebEngineView(self)
        
        # 创建开发者工具管理器
        self.dev_tools_manager = DevToolsManager(self)

        
        # 获取 Web URL
        web_url = app_settings.get_web_url()
        logger_helper.info(f"Web URL from settings: {web_url}")
        
        if web_url:
            if app_settings.is_dev_mode:
                # 开发模式：使用 Vite 开发服务器
                self.web_engine_view.load_url(web_url)
                logger_helper.info(f"Development mode: Loading from {web_url}")
            else:
                # 生产模式：加载本地文件
                self.load_local_html()
        else:
            logger_helper.error("Failed to get web URL")
        
        # 添加 Web 引擎到布局
        layout.addWidget(self.web_engine_view)
        
        # 设置快捷键
        self._setup_shortcuts()
        chat_db_path = os.path.join(app_info.appdata_path, "chats.db")
        self.chat_service = None
        
        # # 创建定时器 Demo 测试使用的
        # self.dashboard_timer = QTimer(self)
        # self.dashboard_timer.timeout.connect(self.update_dashboard_data)
        # self.dashboard_timer.start(5000)  # 每5秒触发一次

    def set_py_login(self, login):
        self.py_login = login

    def get_py_login(self):
        return self.py_login

    def setup_chats(self):
        chat_db_path = self.py_login.main_win.general_settings["chat_db_path"]
        self.chat_service = ChatService(db_path=chat_db_path)


    def load_local_html(self):
        """加载本地 HTML 文件"""
        index_path = app_settings.dist_dir / "index.html"
        logger_helper.info(f"Looking for index.html at: {index_path}")
        
        if index_path.exists():
            try:
                # 直接加载本地文件
                self.web_engine_view.load_local_file(index_path)
                logger_helper.info(f"Production mode: Loading from {index_path}")
                
            except Exception as e:
                logger_helper.error(f"Error loading HTML file: {str(e)}")
                import traceback
                logger_helper.error(traceback.format_exc())
        else:
            logger_helper.error(f"index.html not found in {app_settings.dist_dir}")
            # 列出目录内容以便调试
            if app_settings.dist_dir.exists():
                logger_helper.info(f"Contents of {app_settings.dist_dir}:")
                for item in app_settings.dist_dir.iterdir():
                    logger_helper.info(f"  - {item.name}")
            else:
                logger_helper.error(f"Directory {app_settings.dist_dir} does not exist")
    
    def _setup_shortcuts(self):
        """设置快捷键"""
        # 开发者工具快捷键
        self.dev_tools_shortcut = QShortcut(QKeySequence("F12"), self)
        self.dev_tools_shortcut.activated.connect(self.dev_tools_manager.toggle)
        
        # F5 重新加载
        reload_action = QAction(self)
        reload_action.setShortcut(QKeySequence('F5'))
        reload_action.triggered.connect(self.reload)
        self.addAction(reload_action)
        
        # Ctrl+L 清除日志
        clear_logs_action = QAction(self)
        clear_logs_action.setShortcut(QKeySequence('Ctrl+L'))
        clear_logs_action.triggered.connect(self.dev_tools_manager.clear_all)
        self.addAction(clear_logs_action)

    def self_confirm(self):
        print("self confirming top web gui....")

    def reload(self):
        """重新加载页面"""
        logger_helper.info("Reloading page...")
        if app_settings.is_dev_mode:
            self.web_engine_view.reload_page()
        else:
            self.load_local_html()
    
    def update_dashboard_data(self):
        """更新仪表盘数据"""
        try:
            # 生成随机数据
            data = {
                'overview': random.randint(10, 100),
                'statistics': random.randint(5, 50),
                'recentActivities': random.randint(20, 200),
                'quickActions': random.randint(1, 30)
            }
            
            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Dashboard data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update dashboard data: {response.error}")
            
            IPCAPI.get_instance().refresh_dashboard(data, handle_response)
            
        except Exception as e:
            logger_helper.error(f"Error updating dashboard data: {e}")
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 创建确认对话框
        reply = QMessageBox.question(
            self,
            'Confirm Exit',
            'Are you sure you want to exit the program?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 接受关闭事件
            event.accept()
            # 结束整个应用程序
            sys.exit(0)
        else:
            # 忽略关闭事件
            event.ignore()

    def update_agents_data(self, dataHolder):
        """更新代理数据"""
        try:
            # 生成随机数据
            agents = dataHolder.agents
            dataJS = {"agents": [agent.to_dict() for agent in agents]}

            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Agents data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update Agents data: {response.error}")

            IPCAPI.get_instance().update_agents(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating agents data: {e}")

    def get_ipc_api(self):
        return IPCAPI.get_instance()


    def update_skills_data(self, dataHolder):
        """更新技能数据"""
        try:
            # 生成随机数据
            skills = dataHolder.agent_skills
            dataJS = {'skills': [sk.to_dict() for sk in skills]}

            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Skills data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update Skills data: {response.error}")

            IPCAPI.get_instance().update_skills(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating Skills data: {e}")

    def update_tasks_data(self, dataHolder):
        """更新技能数据"""
        try:
            # 生成随机数据
            agents = dataHolder.agents
            all_tasks = []
            for agent in agents:
                all_tasks.extend(agent.tasks)

            dataJS = {'tasks': [task.to_dict() for task in all_tasks]}

            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Tasks data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update Tasks data: {response.error}")

            IPCAPI.get_instance().update_tasks(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating Tasks data: {e}")


    def update_tools_data(self, dataHolder):
        """更新技能数据"""
        try:
            # 生成随机数据
            dataJS = {'tools': [tool.model_dump() for tool in dataHolder.mcp_tools_schemas]}


            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Tools data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update Tools data: {response.error}")

            IPCAPI.get_instance().update_tools(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating Tools data: {e}")


    def update_knowledge_data(self, dataHolder):
        """更新技能数据"""
        try:
            # 生成随机数据
            knowledges = {}
            dataJS = {"knowledges": knowledges}

            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Knowledge data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update knowledge data: {response.error}")

            IPCAPI.get_instance().update_knowledge(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating knowledge data: {e}")


    def update_settings_data(self, dataHolder):
        """更新技能数据"""
        try:
            # 生成随机数据
            dataJS = {"settings": dataHolder.generaal_settings}

            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Settings data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update settings data: {response.error}")

            IPCAPI.get_instance().update_settings(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating settings data: {e}")



    def update_vehicles_data(self, dataHolder):
        """更新技能数据"""
        try:
            # 生成随机数据
            dataJS = {"vehicles": [v.genJson() for v in dataHolder.vehicles]}

            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Vehicles data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update vehicles data: {response.error}")

            IPCAPI.get_instance().update_vehicles(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating vehicles data: {e}")


    # def update_all(self, dataHolder):
    #     try:
    #         agents = dataHolder.agents
    #         all_tasks = []
    #         for agent in agents:
    #             all_tasks.extend(agent.tasks)

    #         skills = dataHolder.agent_skills
    #         vehicles = dataHolder.vehicles
    #         settings = dataHolder.general_settings
    #         # knowledges = py_login.main_win.knowledges
    #         # chats = py_login.main_win.chats
    #         knowledges = {}
    #         chats = {}
    #         # 生成随机令牌
    #         token = str(uuid.uuid4()).replace('-', '')
    #         # logger.info(f"Get all successful for user: {username}")
    #         dataJS = {
    #             'token': token,
    #             'agents': [agent.to_dict() for agent in agents],
    #             'skills': [sk.to_dict() for sk in skills],
    #             'tools': [tool.model_dump() for tool in dataHolder.mcp_tools_schemas],
    #             'tasks': [task.to_dict() for task in all_tasks],
    #             'vehicles': [vehicle.genJson() for vehicle in vehicles],
    #             'settings': settings,
    #             'knowledges': knowledges,
    #             'chats': chats,
    #             'message': 'Get all successful'
    #         }
    #         print('all dataJS:', dataJS)
    #         def handle_response(response):
    #             if response.success:
    #                 logger_helper.info(f"all data updated successfully: {response.data}")
    #             else:
    #                 logger_helper.error(f"Failed to update all data: {response.error}")

    #         IPCAPI.get_instance().update_all(dataJS, handle_response)

    #     except Exception as e:
    #         logger_helper.error(f"Error updating vehicles data: {e}")

    def receive_new_chat_message(self, dataHolder):
        """add new chat message to data structure and update DB and GUI"""
        try:
            # 生成随机数据
            dataJS = [
                {
                    'id': 1,
                    'session_id': 1,
                    'sender': "12",
                    'chat_id': 2,
                    'is_group': False,
                    'recipients': [],
                    'content': dataHolder["message"],
                    'attachments': [],
                    'tx_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            ]

            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Chats data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update Chats data: {response.error}")

            print("about to update GUI chats data....", data)
            IPCAPI.get_instance().update_chats(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating Chats data: {e}")


    def send_new_chat_message(self, dataHolder):
        """更新聊天数据"""
        try:
            # 生成随机数据
            dataJS = [
                {
                    'id': 1,
                    'session_id': 1,
                    'sender': "12",
                    'chat_id': 2,
                    'is_group': False,
                    'recipients': [],
                    'content': dataHolder["message"],
                    'attachments': [],
                    'tx_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            ]

            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Chats data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update Chats data: {response.error}")

            print("about to update GUI chats data....", data)
            IPCAPI.get_instance().update_chats(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating Chats data: {e}")


    def init_new_chat(self, chat):
        """更新聊天数据"""
        try:
            # 生成随机数据
            dataJS = self.chat_service.create_conversation(chat["name"], chat["is_group"], chat["description"])

            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Chats data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update Chats data: {response.error}")

            print("about to update GUI chats data....", dataJS)
            IPCAPI.get_instance().update_chats(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating Chats data: {e}")

    def delete_chats(self, chat_ids):
        """更新聊天数据"""
        try:
            # 生成随机数据
            dataJS = self.chat_service.delete_conversations(chat_ids)

            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Chats data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update Chats data: {response.error}")

            print("about to update GUI chats data....", dataJS)
            IPCAPI.get_instance().update_chats(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating Chats data: {e}")

    def hide_chats(self, chat_ids):
        """更新聊天数据"""
        try:
            # 生成随机数据
            dataJS = self.chat_service.hide_conversations(chat_ids)

            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Chats data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update Chats data: {response.error}")

            print("about to update GUI chats data....", data)
            IPCAPI.get_instance().update_chats(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating Chats data: {e}")


    def delete_chat_messages(self, msg_ids):
        """更新聊天数据"""
        try:
            # 生成随机数据
            dataJS = self.chat_service.delete_messages(msg_ids)

            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Chats data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update Chats data: {response.error}")

            print("about to update GUI chats data....", data)
            IPCAPI.get_instance().update_chats(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating Chats data: {e}")

    def delete_all_chat_messages(self, chat_id):
        """更新聊天数据"""
        try:
            # 生成随机数据
            dataJS = self.chat_service.delete_conversation(chat_id)

            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Chats data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update Chats data: {response.error}")

            print("about to update GUI chats data....", dataJS)
            IPCAPI.get_instance().update_chats(dataJS, handle_response)

        except Exception as e:
            logger_helper.error(f"Error updating Chats data: {e}")