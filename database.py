import sqlite3
import os
from typing import List, Optional, Tuple
from astrbot.api import logger


class SunosDatabase:
    """Sunos 插件数据库管理类"""

    def __init__(self, db_path: str = None):
        # 数据存储在AstrBot全局data目录下，而非插件目录
        if db_path is None:
            # 获取AstrBot的data目录路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 从 data/plugins/sunos 回到 data 目录
            data_dir = os.path.dirname(os.path.dirname(current_dir))
            self.db_path = os.path.join(data_dir, "sunos_plugin.db")
        else:
            self.db_path = db_path

        self._ensure_data_dir()
        self._init_database()

    def _ensure_data_dir(self):
        """确保数据目录存在"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _init_database(self):
        """初始化数据库表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 词库表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS keywords (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT NOT NULL,
                        reply TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 欢迎语表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS welcome_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id TEXT NOT NULL UNIQUE,
                        message TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 群聊开关表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS group_settings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id TEXT NOT NULL UNIQUE,
                        enabled BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                conn.commit()
                logger.info("Sunos 数据库初始化完成")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")

    # 词库管理
    def add_keyword(self, keyword: str, reply: str) -> bool:
        """添加词库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 检查是否已存在
                cursor.execute("SELECT id FROM keywords WHERE keyword = ?", (keyword,))
                if cursor.fetchone():
                    return False

                cursor.execute(
                    "INSERT INTO keywords (keyword, reply) VALUES (?, ?)",
                    (keyword, reply),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"添加词库失败: {e}")
            return False

    def delete_keyword(self, keyword_id: int) -> bool:
        """删除词库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM keywords WHERE id = ?", (keyword_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除词库失败: {e}")
            return False

    def get_all_keywords(self) -> List[Tuple[int, str, str]]:
        """获取所有词库"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, keyword, reply FROM keywords ORDER BY id")
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取词库失败: {e}")
            return []

    def find_keyword_reply(self, message: str) -> Optional[str]:
        """精确查找关键词回复"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT reply FROM keywords WHERE keyword = ?", (message.strip(),)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"查找关键词失败: {e}")
            return None

    # 欢迎语管理
    def set_welcome_message(self, group_id: str, message: str) -> bool:
        """设置欢迎语"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO welcome_messages (group_id, message, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                    (group_id, message),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"设置欢迎语失败: {e}")
            return False

    def delete_welcome_message(self, group_id: str) -> bool:
        """删除欢迎语"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM welcome_messages WHERE group_id = ?", (group_id,)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"删除欢迎语失败: {e}")
            return False

    def get_welcome_message(self, group_id: str) -> Optional[str]:
        """获取欢迎语"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT message FROM welcome_messages WHERE group_id = ?",
                    (group_id,),
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"获取欢迎语失败: {e}")
            return None

    # 群聊开关管理
    def set_group_enabled(self, group_id: str, enabled: bool) -> bool:
        """设置群聊开关"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO group_settings (group_id, enabled, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                    (group_id, enabled),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"设置群聊开关失败: {e}")
            return False

    def is_group_enabled(self, group_id: str) -> bool:
        """检查群聊是否开启"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT enabled FROM group_settings WHERE group_id = ?", (group_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else True  # 默认开启
        except Exception as e:
            logger.error(f"检查群聊开关失败: {e}")
            return True
