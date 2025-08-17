"""数据库操作层 - 专注于数据持久化

提供干净的数据访问接口，不包含业务逻辑
"""
import sqlite3
import os
from typing import List, Optional, Tuple
from astrbot.api import logger


class SunosDatabase:
    """Sunos 插件数据库管理类 - 纯数据访问层"""

    def __init__(self, db_path: str = None):
        # 数据存储在AstrBot全局data目录下，而非插件目录
        if db_path is None:
            # 获取AstrBot的data目录路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 从 data/plugins/sunos/core 回到 data 目录
            data_dir = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
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
                
                self._create_keywords_table(cursor)
                self._create_welcome_messages_table(cursor)
                self._create_group_settings_table(cursor)
                self._create_blacklist_table(cursor)
                self._create_indexes(cursor)
                
                conn.commit()
                logger.info("Sunos 数据库初始化完成")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")

    def _create_keywords_table(self, cursor):
        """创建词库表结构
        
        表结构设计：
        - id: 自增主键，唯一标识每个词库条目
        - keyword: 关键词文本，用户触发的文本内容
        - reply: 回复内容，支持换行和特殊字符
        - created_at: 创建时间戳，自动记录添加时间
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                reply TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _create_welcome_messages_table(self, cursor):
        """创建欢迎语表结构
        
        表结构设计：
        - id: 自增主键
        - group_id: 群组ID，唯一标识群聊
        - message: 欢迎语内容，支持占位符{user}和{group}
        - created_at: 创建时间
        - updated_at: 更新时间，每次修改欢迎语时更新
        
        约束：group_id设为UNIQUE，确保每个群只有一条欢迎语
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS welcome_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL UNIQUE,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _create_group_settings_table(self, cursor):
        """创建群聊设置表结构
        
        表结构设计：
        - id: 自增主键
        - group_id: 群组ID，唯一标识群聊
        - enabled: 功能开关，TRUE为开启，FALSE为关闭
        - created_at: 创建时间
        - updated_at: 更新时间
        
        约束：group_id设为UNIQUE，确保每个群只有一条设置记录
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS group_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL UNIQUE,
                enabled BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _create_blacklist_table(self, cursor):
        """创建黑名单表结构
        
        表结构设计：
        - id: 自增主键
        - user_id: 用户ID，被拉黑的用户
        - group_id: 群组ID，NULL表示全局黑名单
        - reason: 拉黑原因，可选字段
        - added_by: 添加者ID，记录操作人员
        - created_at: 创建时间
        - updated_at: 更新时间
        
        约束：UNIQUE(user_id, group_id) 防止重复拉黑
        """
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                group_id TEXT,  -- NULL表示全局黑名单，否则为群组特定黑名单
                reason TEXT DEFAULT '',
                added_by TEXT NOT NULL,  -- 添加者的user_id
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, group_id)  -- 防重复：同一用户在同一群（或全局）只能有一条记录
            )
        """)

    def _create_indexes(self, cursor):
        """创建数据库索引以优化查询性能
        
        索引策略：
        - blacklist表的user_id索引：快速查找用户是否在黑名单
        - blacklist表的group_id索引：快速获取特定群的黑名单
        
        这些索引显著提升黑名单检查和列表查询的性能
        """
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_blacklist_user_id ON blacklist(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_blacklist_group_id ON blacklist(group_id)
        """)

    # ==================== 词库管理 ====================
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

    # ==================== 欢迎语管理 ====================
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

    # ==================== 群聊开关管理 ====================
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

    # ==================== 黑名单管理 ====================
    def add_to_blacklist(
        self, user_id: str, added_by: str, group_id: str = None, reason: str = ""
    ) -> bool:
        """添加用户到黑名单"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO blacklist (user_id, group_id, reason, added_by, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (user_id, group_id, reason, added_by),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"添加黑名单失败: {e}")
            return False

    def remove_from_blacklist(self, user_id: str, group_id: str = None) -> bool:
        """从黑名单移除用户"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if group_id is None:
                    cursor.execute(
                        "DELETE FROM blacklist WHERE user_id = ? AND group_id IS NULL",
                        (user_id,),
                    )
                else:
                    cursor.execute(
                        "DELETE FROM blacklist WHERE user_id = ? AND group_id = ?",
                        (user_id, group_id),
                    )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"移除黑名单失败: {e}")
            return False

    def is_in_blacklist(self, user_id: str, group_id: str = None) -> bool:
        """检查用户是否在黑名单中"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 检查全局黑名单
                cursor.execute(
                    "SELECT 1 FROM blacklist WHERE user_id = ? AND group_id IS NULL",
                    (user_id,),
                )
                if cursor.fetchone():
                    return True

                # 检查群组黑名单（如果提供了group_id）
                if group_id:
                    cursor.execute(
                        "SELECT 1 FROM blacklist WHERE user_id = ? AND group_id = ?",
                        (user_id, group_id),
                    )
                    if cursor.fetchone():
                        return True

                return False
        except Exception as e:
            logger.error(f"检查黑名单失败: {e}")
            return False

    def get_blacklist(
        self, group_id: str = None, limit: int = 50, offset: int = 0
    ) -> List[Tuple]:
        """获取黑名单列表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if group_id == "all":
                    # 获取所有黑名单
                    cursor.execute(
                        """
                        SELECT id, user_id, group_id, reason, added_by, created_at
                        FROM blacklist
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?
                        """,
                        (limit, offset),
                    )
                elif group_id is None:
                    # 获取全局黑名单
                    cursor.execute(
                        """
                        SELECT id, user_id, group_id, reason, added_by, created_at
                        FROM blacklist
                        WHERE group_id IS NULL
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?
                        """,
                        (limit, offset),
                    )
                else:
                    # 获取指定群组黑名单
                    cursor.execute(
                        """
                        SELECT id, user_id, group_id, reason, added_by, created_at
                        FROM blacklist
                        WHERE group_id = ?
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?
                        """,
                        (group_id, limit, offset),
                    )

                return cursor.fetchall()
        except Exception as e:
            logger.error(f"获取黑名单失败: {e}")
            return []

    def get_user_blacklist_info(
        self, user_id: str, group_id: str = None
    ) -> Optional[Tuple]:
        """获取用户的黑名单信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 优先检查群组黑名单
                if group_id:
                    cursor.execute(
                        """
                        SELECT id, user_id, group_id, reason, added_by, created_at
                        FROM blacklist
                        WHERE user_id = ? AND group_id = ?
                        """,
                        (user_id, group_id),
                    )
                    result = cursor.fetchone()
                    if result:
                        return result

                # 检查全局黑名单
                cursor.execute(
                    """
                    SELECT id, user_id, group_id, reason, added_by, created_at
                    FROM blacklist
                    WHERE user_id = ? AND group_id IS NULL
                    """,
                    (user_id,),
                )
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"获取用户黑名单信息失败: {e}")
            return None