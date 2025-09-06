from sqlalchemy.orm import  sessionmaker
from agent.chats.chats_db import get_engine, get_session_factory, Base
from agent.ec_skills.agent_skills_db import DBAgentSkill
from agent.ec_agents.agent_db import DBAgent, DBAgentTool, DBAgentTask, DBAgentKnowledge
from agent.chats.chat_service import SingletonMeta

from contextlib import contextmanager
from sqlalchemy.exc import SQLAlchemyError
import re


class AgentsDBService(metaclass=SingletonMeta):
    """聊天系统服务类，提供所有聊天相关的操作接口"""

    def __init__(self, db_path: str = None, engine=None, session=None):
        """
        初始化聊天服务

        Args:
            db_path (str, optional): 数据库文件路径
            engine: SQLAlchemy引擎实例
            session: SQLAlchemy会话实例
        """
        if session is not None:
            self.SessionFactory = lambda: session
        elif engine is not None:
            self.SessionFactory = sessionmaker(bind=engine)
        elif db_path is not None:
            engine = get_engine(db_path)
            self.SessionFactory = get_session_factory(db_path)
            Base.metadata.create_all(engine)
            # 新增：自动插入初始 db_version 记录并执行数据库升级
            try:
                from agent.chats.db_migration import DBMigration
                migrator = DBMigration(db_path)
                # 确保有 db_version 表和初始记录
                migrator.get_current_version()
                migrator.upgrade_to_version('2.0.0', description='自动升级到2.0.0，添加chat_notification表')
            except Exception as e:
                print(f"[DBMigration] 数据库升级失败: {e}")
        else:
            raise ValueError("Must provide db_path, engine or session")

    @contextmanager
    def session_scope(self):
        """事务管理器，确保线程安全"""
        session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------- response helpers ----------
    def _success(self, **kwargs):
        return {"success": True, **kwargs, "error": None}

    def _fail(self, error: str, **kwargs):
        return {"success": False, **kwargs, "data": None, "error": error}

    # ========== internal generic helpers =============================
    def _add(self, model, data: dict):
        """Upsert: insert new row or update existing when id clashes."""
        if not isinstance(data, dict) or 'id' not in data:
            return self._fail("'data' must include primary key 'id'", id=None)
        item_id = data['id']
        try:
            with self.session_scope() as s:
                obj = s.get(model, item_id)
                if obj:
                    # update existing
                    for k, v in data.items():
                        if hasattr(obj, k):
                            setattr(obj, k, v)
                    s.flush()
                    return self._success(id=item_id, data=obj.to_dict())
                # create new
                obj = model(**data)
                s.add(obj)
                s.flush()
                return self._success(id=obj.id, data=obj.to_dict())
        except SQLAlchemyError as e:
            return self._fail(str(e), id=item_id)

    def _delete(self, model, item_id: str):
        try:
            with self.session_scope() as s:
                obj = s.get(model, item_id)
                if not obj:
                    return self._fail(f"{model.__name__} {item_id} not found", id=item_id)
                s.delete(obj)
                s.flush()
                return self._success(id=item_id, data=None)
        except SQLAlchemyError as e:
            return self._fail(str(e), id=item_id)

    def _update(self, model, item_id: str, fields: dict):
        try:
            with self.session_scope() as s:
                obj = s.get(model, item_id)
                if not obj:
                    return self._fail(f"{model.__name__} {item_id} not found", id=item_id)
                for k, v in fields.items():
                    if hasattr(obj, k):
                        setattr(obj, k, v)
                s.flush()
                return self._success(id=item_id, data=obj.to_dict())
        except SQLAlchemyError as e:
            return self._fail(str(e), id=item_id)

    def _search(self, model, id_: str = None, name: str = None, desc_regex: str = None):
        try:
            with self.session_scope() as s:
                q = s.query(model)
                if id_:
                    q = q.filter(model.id == id_)
                if name:
                    q = q.filter(model.name.ilike(f"%{name}%"))
                results = q.all()
                if desc_regex:
                    pattern = re.compile(desc_regex, re.IGNORECASE)
                    results = [r for r in results if pattern.search(getattr(r, 'description', '') or '')]
                return [r.to_dict() for r in results]
        except SQLAlchemyError as e:
            print(f"[SearchError] {e}")
            return []

    # ========== public CRUD wrappers =================================
    # ---- Agents ----

    def add_agent(self, data):
        return self._add(DBAgent, data)

    def delete_agent(self, agent_id):
        return self._delete(DBAgent, agent_id)

    def update_agent(self, agent_id, fields):
        return self._update(DBAgent, agent_id, fields)

    def query_agents(self, id=None, name=None, description=None):
        return {"success": True,
                "data": self._search(DBAgent, id, name, description),
                "error": None}

    # ---- Skills ----
    def add_skill(self, data):
        return self._add(DBAgentSkill, data)

    def delete_skill(self, skill_id):
        return self._delete(DBAgentSkill, skill_id)

    def update_skill(self, skill_id, fields):
        return self._update(DBAgentSkill, skill_id, fields)

    def query_skills(self, id=None, name=None, description=None):
        return {"success": True,
                "data": self._search(DBAgentSkill, id, name, description),
                "error": None}

    # ---- Tasks ----
    def add_task(self, data):
        return self._add(DBAgentTask, data)

    def delete_task(self, task_id):
        return self._delete(DBAgentTask, task_id)

    def update_task(self, task_id, fields):
        return self._update(DBAgentTask, task_id, fields)

    def query_tasks(self, id=None, name=None, description=None):
        return {"success": True,
                "data": self._search(DBAgentTask, id, name, description),
                "error": None}

    # ---- Tools ----
    def add_tool(self, data):
        return self._add(DBAgentTool, data)

    def delete_tool(self, tool_id):
        return self._delete(DBAgentTool, tool_id)

    def update_tool(self, tool_id, fields):
        return self._update(DBAgentTool, tool_id, fields)

    def query_tools(self, id=None, name=None, description=None):
        return {"success": True,
                "data": self._search(DBAgentTool, id, name, description),
                "error": None}

    # ---- Knowledges ----
    def add_knowledge(self, data):
        return self._add(DBAgentKnowledge, data)

    def delete_knowledge(self, kn_id):
        return self._delete(DBAgentKnowledge, kn_id)

    def update_knowledge(self, kn_id, fields):
        return self._update(DBAgentKnowledge, kn_id, fields)

    def query_knowledges(self, id=None, name=None, description=None):
        return {"success": True,
                "data": self._search(DBAgentKnowledge, id, name, description),
                "error": None}