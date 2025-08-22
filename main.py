"""SunKeyword 智能词库回复插件

专注于关键词自动回复功能的智能插件
版本：4.2.0
作者：Akuma
"""

import json
import os
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


class SunKeywordException(Exception):
    """插件基础异常类"""
    pass


class DataValidationError(SunKeywordException):
    """数据验证异常"""
    pass


class FileOperationError(SunKeywordException):
    """文件操作异常"""
    pass


@dataclass
class KeywordEntry:
    """关键词条目数据类"""
    keyword: str
    reply: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {"keyword": self.keyword, "reply": self.reply}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KeywordEntry":
        if not isinstance(data, dict):
            raise DataValidationError("关键词数据必须是字典格式")
        
        keyword = data.get("keyword", "").strip()
        reply = data.get("reply", "").strip()
        
        if not keyword:
            raise DataValidationError("关键词不能为空")
        if not reply:
            raise DataValidationError("回复内容不能为空")
            
        return cls(keyword=keyword, reply=reply)


class PluginConstants:
    """插件常量定义"""
    PLUGIN_NAME = "sunkeyword"
    PLUGIN_VERSION = "4.2.0"
    PLUGIN_AUTHOR = "Akuma"
    PLUGIN_DESCRIPTION = "SunKeyword 智能词库回复插件"
    PLUGIN_URL = "https://github.com/Akuma-real/sunos-sunkeyword"
    
    COMMAND_PREFIXES = ["/sunos", ".sunos"]
    SUBCOMMAND_NAMESPACE = "ck"
    
    EMPTY_KEYWORDS_MESSAGE = "📭 当前没有词库记录"
    KEYWORDS_LIST_HEADER = "📚 当前词库列表:"
    COMMAND_USAGE_MESSAGE = "📖 用法: /sunos ck <help|list>"
    UNKNOWN_COMMAND_MESSAGE = "❓ 未知操作，使用 /sunos ck help 查看帮助"
    
    HELP_DOCUMENTATION = """🌟 SunKeyword 使用指南:

📋 可用命令：
- /sunos ck list         查看当前词库
- /sunos ck help         显示此帮助信息

💡 小贴士：
• 支持 .sunos 前缀，例如：.sunos ck list
• 关键词匹配不区分大小写"""
    
    SELF_TRIGGER_INDICATORS = [
        "📚 当前词库列表", "📭 当前没有词库记录",
        "🌟 SunKeyword 使用指南"
    ]
    
    DEFAULT_KEYWORDS_FILENAME = "keywords.json"
    JSON_ENCODING = "utf-8"
    JSON_INDENT = 2
    MAX_PREVIEW_LENGTH = 30
    MAX_KEYWORDS_DISPLAY = 100


class CaseInsensitiveMatchingStrategy:
    """大小写不敏感匹配策略"""
    
    def matches(self, keyword: str, message: str) -> bool:
        if not isinstance(keyword, str) or not isinstance(message, str):
            return False
        return keyword.strip().casefold() == message.strip().casefold()


class TextProcessor:
    """文本处理工具类"""
    
    @staticmethod
    def normalize_text(text: str) -> str:
        if not isinstance(text, str):
            return str(text) if text is not None else ""
        
        try:
            normalized = text.replace("\\n", "\n")
            normalized = normalized.replace("\\t", "\t")
            normalized = normalized.replace("\\r", "\r")
            return normalized
        except (AttributeError, TypeError) as e:
            logger.warning(f"文本规范化失败: {e}")
            return str(text)
    
    @staticmethod  
    def create_reply_preview(reply: str, max_length: int = None) -> str:
        if max_length is None:
            max_length = PluginConstants.MAX_PREVIEW_LENGTH
            
        if not reply or max_length <= 0:
            return ""
        
        normalized = TextProcessor.normalize_text(reply)
        cleaned = re.sub(r'\s+', ' ', normalized.strip())
        
        if len(cleaned) > max_length:
            return cleaned[:max_length] + "..."
        return cleaned
    
    @staticmethod
    def format_keyword_list(keywords: List[KeywordEntry]) -> str:
        if not keywords:
            return PluginConstants.EMPTY_KEYWORDS_MESSAGE
        
        display_keywords = keywords[:PluginConstants.MAX_KEYWORDS_DISPLAY]
        lines = [PluginConstants.KEYWORDS_LIST_HEADER, ""]
        
        for index, entry in enumerate(display_keywords, 1):
            preview = TextProcessor.create_reply_preview(entry.reply)
            lines.append(f"{index:2d}. {entry.keyword} → {preview}")
        
        total_count = len(keywords)
        if total_count > PluginConstants.MAX_KEYWORDS_DISPLAY:
            lines.append(f"\n... 还有 {total_count - PluginConstants.MAX_KEYWORDS_DISPLAY} 条记录未显示")
        
        lines.append(f"\n📊 共 {total_count} 条记录")
        return TextProcessor.normalize_text("\n".join(lines))


class InputValidator:
    """输入验证工具类"""
    
    @staticmethod
    def is_command_message(text: str) -> bool:
        if not isinstance(text, str):
            return False
        
        trimmed = text.strip().lower()
        if not trimmed:
            return False
        
        return any(
            trimmed.startswith(prefix.lower()) 
            for prefix in PluginConstants.COMMAND_PREFIXES
        )
    
    @staticmethod
    def is_self_trigger_message(text: str) -> bool:
        if not isinstance(text, str):
            return False
        
        return any(
            indicator in text 
            for indicator in PluginConstants.SELF_TRIGGER_INDICATORS
        )


class FileManager:
    """文件管理工具类"""
    
    def __init__(self, file_path: str):
        self.file_path = os.path.abspath(file_path)
        self._ensure_file_directory()
    
    def _ensure_file_directory(self) -> None:
        directory = os.path.dirname(self.file_path)
        if directory and not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as e:
                raise FileOperationError(f"创建目录失败: {e}", directory)
    
    def load_keywords_from_file(self) -> List[KeywordEntry]:
        if not os.path.exists(self.file_path):
            logger.info(f"关键词文件不存在，返回空列表: {self.file_path}")
            return []
        
        raw_data = self._read_json_file()
        return self._parse_keyword_entries(raw_data)
    
    def _read_json_file(self) -> List[Dict[str, Any]]:
        try:
            with open(self.file_path, 'r', encoding=PluginConstants.JSON_ENCODING) as file:
                raw_data = json.load(file)
            
            if not isinstance(raw_data, list):
                raise DataValidationError("JSON根元素必须是数组格式")
            
            return raw_data
            
        except json.JSONDecodeError as e:
            raise FileOperationError(f"JSON文件解析失败: {e}")
        except PermissionError as e:
            raise FileOperationError(f"文件访问权限不足: {e}")
        except OSError as e:
            raise FileOperationError(f"文件系统错误: {e}")
    
    def _parse_keyword_entries(self, raw_data: List[Dict[str, Any]]) -> List[KeywordEntry]:
        keyword_entries = []
        
        for index, item_data in enumerate(raw_data):
            try:
                entry = KeywordEntry.from_dict(item_data)
                keyword_entries.append(entry)
            except DataValidationError as e:
                logger.warning(f"跳过无效的关键词条目 #{index + 1}: {e}")
                continue
        
        logger.info(f"成功加载 {len(keyword_entries)} 条关键词")
        return keyword_entries


class HelpCommand:
    """帮助命令实现"""
    
    def execute(self, event: AstrMessageEvent, args: List[str]) -> str:
        logger.info("执行帮助命令")
        return PluginConstants.HELP_DOCUMENTATION


class ListCommand:
    """列表命令实现"""
    
    def __init__(self, keyword_manager):
        self.keyword_manager = keyword_manager
    
    def execute(self, event: AstrMessageEvent, args: List[str]) -> str:
        try:
            logger.info("执行列表命令")
            keywords = self.keyword_manager.get_all_keywords()
            return TextProcessor.format_keyword_list(keywords)
        except Exception as e:
            logger.error(f"执行列表命令失败: {e}")
            return "❌ 获取词库列表失败，请稍后重试"


class CommandProcessor:
    """命令处理器"""
    
    def __init__(self, keyword_manager):
        self.keyword_manager = keyword_manager
        self.commands = {}
        self._register_commands()
    
    def _register_commands(self) -> None:
        help_command = HelpCommand()
        self.commands["help"] = help_command
        self.commands["h"] = help_command
        self.commands["?"] = help_command
        
        list_command = ListCommand(self.keyword_manager)
        self.commands["list"] = list_command
        self.commands["ls"] = list_command
    
    def process_command(self, event: AstrMessageEvent, args: List[str]) -> str:
        if len(args) < 3:
            return PluginConstants.COMMAND_USAGE_MESSAGE
        
        command_name = args[2].lower()
        
        if command_name in self.commands:
            try:
                return self.commands[command_name].execute(event, args)
            except Exception as e:
                logger.error(f"命令 '{command_name}' 执行失败: {e}")
                return f"❌ 命令执行失败: {str(e)}"
        else:
            return PluginConstants.UNKNOWN_COMMAND_MESSAGE


class KeywordManager:
    """关键词管理器"""
    
    def __init__(self, file_path: str, matching_strategy = None):
        self.file_manager = FileManager(file_path)
        self.matching_strategy = matching_strategy or CaseInsensitiveMatchingStrategy()
        self._keywords_cache: Optional[List[KeywordEntry]] = None
        self._cache_valid: bool = False
        
        logger.info("关键词管理器初始化完成")
    
    def _invalidate_cache(self) -> None:
        self._keywords_cache = None
        self._cache_valid = False
    
    def _is_cache_valid(self) -> bool:
        return self._cache_valid and self._keywords_cache is not None
    
    def get_all_keywords(self, force_reload: bool = False) -> List[KeywordEntry]:
        if not force_reload and self._is_cache_valid():
            return self._keywords_cache
        
        try:
            self._keywords_cache = self.file_manager.load_keywords_from_file()
            self._cache_valid = True
            return self._keywords_cache
        except (FileOperationError, DataValidationError) as e:
            logger.error(f"加载关键词失败: {e}")
            return []
    
    def find_matching_reply(self, message: str) -> Optional[str]:
        if not isinstance(message, str) or not message.strip():
            return None
        
        keywords = self.get_all_keywords()
        
        for entry in keywords:
            if self.matching_strategy.matches(entry.keyword, message):
                logger.debug(f"关键词匹配成功: '{entry.keyword}' -> '{message}'")
                return TextProcessor.normalize_text(entry.reply)
        
        return None


@register(
    PluginConstants.PLUGIN_NAME,
    PluginConstants.PLUGIN_AUTHOR,
    PluginConstants.PLUGIN_DESCRIPTION,
    PluginConstants.PLUGIN_VERSION,
    PluginConstants.PLUGIN_URL,
)
class SunKeywordPlugin(Star):
    """SunKeyword 智能词库回复插件主类"""
    
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.context = context
        
        self.keywords_file_path = os.path.join(
            os.path.dirname(__file__), 
            PluginConstants.DEFAULT_KEYWORDS_FILENAME
        )
        
        try:
            self.keyword_manager = KeywordManager(
                self.keywords_file_path,
                CaseInsensitiveMatchingStrategy()
            )
            
            self.command_processor = CommandProcessor(self.keyword_manager)
            
            logger.info(f"🚀 SunKeyword 插件 v{PluginConstants.PLUGIN_VERSION} 初始化成功")
            
        except Exception as e:
            logger.error(f"❌ 插件初始化失败: {e}")
            raise SunKeywordException(f"插件初始化失败: {e}")
    
    def _parse_command_arguments(self, message: str) -> List[str]:
        if not isinstance(message, str):
            return []
        
        cleaned_message = message.strip()
        if not cleaned_message:
            return []
        
        return cleaned_message.split()
    
    @filter.command("sunos")
    async def handle_sunos_slash_command(self, event: AstrMessageEvent):
        async for result in self._process_sunos_command(event):
            yield result
    
    @filter.command_group("sunos")
    async def handle_sunos_dot_command(self, event: AstrMessageEvent):
        async for result in self._process_sunos_command(event):
            yield result
    
    async def _process_sunos_command(self, event: AstrMessageEvent):
        try:
            args = self._parse_command_arguments(event.message_str)
            
            if len(args) < 2:
                return
            
            if args[1] == PluginConstants.SUBCOMMAND_NAMESPACE:
                result_message = self.command_processor.process_command(event, args)
                yield event.plain_result(result_message)
            
        except Exception as e:
            logger.error(f"处理 sunos 命令时发生错误: {e}")
            yield event.plain_result("❌ 系统错误，请稍后重试")
    
    @filter.event_message_type(filter.EventMessageType.ALL, priority=1)
    async def handle_auto_reply_messages(self, event: AstrMessageEvent, context: Context = None, *args, **kwargs):
        try:
            user_message = event.message_str
            if not isinstance(user_message, str):
                return
            
            trimmed_message = user_message.strip()
            if not trimmed_message:
                return
            
            if InputValidator.is_command_message(trimmed_message):
                return
            
            if InputValidator.is_self_trigger_message(trimmed_message):
                return
            
            reply_content = self.keyword_manager.find_matching_reply(user_message)
            if reply_content:
                logger.debug(f"触发自动回复，消息: '{trimmed_message[:50]}...'")
                yield event.plain_result(reply_content)
                
        except Exception as e:
            logger.error(f"自动回复处理失败: {e}")
    
    async def terminate(self):
        try:
            logger.info(f"👋 SunKeyword 插件 v{PluginConstants.PLUGIN_VERSION} 正在卸载...")
            
            if hasattr(self, 'keyword_manager'):
                self.keyword_manager._invalidate_cache()
            
            logger.info("✅ SunKeyword 插件卸载完成")
            
        except Exception as e:
            logger.error(f"❌ 插件卸载时发生错误: {e}")


if __name__ == "__main__":
    print(f"SunKeyword 插件 v{PluginConstants.PLUGIN_VERSION}")
    print("这是一个 AstrBot 插件文件，不应直接运行。")
    print("请将此文件放置在 AstrBot 的插件目录中。")