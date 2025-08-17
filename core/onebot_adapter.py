"""OneBot11 API适配器模块

基于OneBot11标准实现的HTTP API客户端，用于与支持OneBot11协议的机器人实例通信。
支持发送消息、群管理、成员操作等核心功能。

主要特性：
- 异步HTTP客户端（基于aiohttp）
- 完整的错误处理和重试机制
- 连接池和会话管理
- 类型安全的API接口
- 可配置的超时和重试策略
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass

import aiohttp
from aiohttp import ClientTimeout, ClientError, ClientConnectorError

logger = logging.getLogger(__name__)


class OneBotApiError(Exception):
    """OneBot API调用异常基类"""
    
    def __init__(self, message: str, status_code: int = None, response_data: Dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class OneBotNetworkError(OneBotApiError):
    """网络连接异常"""
    pass


class OneBotTimeoutError(OneBotApiError):
    """请求超时异常"""
    pass


class OneBotResponseError(OneBotApiError):
    """API响应错误异常"""
    pass


@dataclass
class OneBotConfig:
    """OneBot配置数据类"""
    base_url: str
    access_token: Optional[str] = None
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    
    def __post_init__(self):
        """配置验证"""
        if not self.base_url:
            raise ValueError("base_url不能为空")
        
        # 确保URL格式正确
        if not self.base_url.startswith(('http://', 'https://')):
            self.base_url = f"http://{self.base_url}"
        
        # 移除末尾斜杠
        self.base_url = self.base_url.rstrip('/')


@dataclass
class ApiResponse:
    """API响应数据类"""
    success: bool
    data: Any = None
    error_message: str = ""
    status_code: int = 200
    
    @classmethod
    def from_dict(cls, response_dict: Dict) -> 'ApiResponse':
        """从响应字典创建ApiResponse实例"""
        status = response_dict.get('status', 'failed')
        retcode = response_dict.get('retcode', -1)
        
        success = status == 'ok' and retcode == 0
        data = response_dict.get('data')
        error_message = response_dict.get('message', '') if not success else ""
        
        return cls(
            success=success,
            data=data,
            error_message=error_message
        )


class OneBotAdapter:
    """OneBot11 HTTP API适配器
    
    提供与OneBot11标准兼容的HTTP API接口，支持：
    - 消息发送（私聊/群聊）
    - 群管理操作（踢人、禁言等）
    - 信息获取（用户信息、群成员列表等）
    - 完整的错误处理和重试机制
    """
    
    def __init__(self, config: OneBotConfig):
        """初始化适配器
        
        Args:
            config: OneBot配置对象
        """
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._closed = False
        
        # 请求头设置
        self._headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'SunOS-OneBot-Adapter/2.0'
        }
        
        if config.access_token:
            self._headers['Authorization'] = f'Bearer {config.access_token}'
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
    
    async def _ensure_session(self):
        """确保HTTP会话已创建"""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers=self._headers,
                connector=aiohttp.TCPConnector(limit=100, limit_per_host=30)
            )
    
    async def close(self):
        """关闭HTTP会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        self._closed = True
    
    async def _make_request(self, endpoint: str, data: Dict, method: str = 'POST') -> ApiResponse:
        """发起HTTP请求
        
        Args:
            endpoint: API端点
            data: 请求数据
            method: HTTP方法
            
        Returns:
            ApiResponse对象
            
        Raises:
            OneBotApiError: API调用异常
        """
        if self._closed:
            raise OneBotApiError("适配器已关闭")
        
        await self._ensure_session()
        url = f"{self.config.base_url}/{endpoint.lstrip('/')}"
        
        for attempt in range(self.config.max_retries + 1):
            try:
                logger.debug(f"OneBot API请求 [{attempt+1}/{self.config.max_retries+1}]: {method} {url}")
                
                async with self._session.request(method, url, json=data) as response:
                    response_text = await response.text()
                    
                    # 记录响应
                    logger.debug(f"OneBot API响应 [{response.status}]: {response_text}")
                    
                    if response.status >= 400:
                        # HTTP错误状态码
                        error_msg = f"HTTP {response.status}: {response.reason}"
                        if response_text:
                            try:
                                error_data = json.loads(response_text)
                                error_msg = error_data.get('message', error_msg)
                            except json.JSONDecodeError:
                                pass
                        
                        if response.status >= 500 and attempt < self.config.max_retries:
                            # 服务器错误，重试
                            logger.warning(f"服务器错误，{self.config.retry_delay}秒后重试: {error_msg}")
                            await asyncio.sleep(self.config.retry_delay)
                            continue
                        
                        raise OneBotResponseError(error_msg, response.status)
                    
                    # 解析响应
                    try:
                        response_data = json.loads(response_text) if response_text else {}
                    except json.JSONDecodeError as e:
                        raise OneBotResponseError(f"响应JSON解析失败: {e}")
                    
                    return ApiResponse.from_dict(response_data)
                    
            except ClientConnectorError as e:
                error_msg = f"连接失败: {e}"
                if attempt < self.config.max_retries:
                    logger.warning(f"{error_msg}，{self.config.retry_delay}秒后重试")
                    await asyncio.sleep(self.config.retry_delay)
                    continue
                raise OneBotNetworkError(error_msg)
                
            except asyncio.TimeoutError:
                error_msg = f"请求超时 ({self.config.timeout}秒)"
                if attempt < self.config.max_retries:
                    logger.warning(f"{error_msg}，{self.config.retry_delay}秒后重试")
                    await asyncio.sleep(self.config.retry_delay)
                    continue
                raise OneBotTimeoutError(error_msg)
                
            except ClientError as e:
                error_msg = f"客户端错误: {e}"
                if attempt < self.config.max_retries:
                    logger.warning(f"{error_msg}，{self.config.retry_delay}秒后重试")
                    await asyncio.sleep(self.config.retry_delay)
                    continue
                raise OneBotApiError(error_msg)
        
        # 不应该到达这里
        raise OneBotApiError("重试次数耗尽")
    
    async def send_private_message(self, user_id: Union[str, int], message: str) -> Tuple[bool, str]:
        """发送私聊消息
        
        Args:
            user_id: 用户ID
            message: 消息内容
            
        Returns:
            (成功状态, 响应消息)
        """
        try:
            data = {
                'user_id': int(user_id),
                'message': message
            }
            
            response = await self._make_request('send_private_msg', data)
            
            if response.success:
                message_id = response.data.get('message_id') if response.data else None
                return True, f"私聊消息发送成功 (ID: {message_id})"
            else:
                return False, f"私聊消息发送失败: {response.error_message}"
                
        except OneBotApiError as e:
            logger.error(f"发送私聊消息异常: {e}")
            return False, f"发送私聊消息异常: {e}"
    
    async def send_group_message(self, group_id: Union[str, int], message: str) -> Tuple[bool, str]:
        """发送群聊消息
        
        Args:
            group_id: 群ID
            message: 消息内容
            
        Returns:
            (成功状态, 响应消息)
        """
        try:
            data = {
                'group_id': int(group_id),
                'message': message
            }
            
            response = await self._make_request('send_group_msg', data)
            
            if response.success:
                message_id = response.data.get('message_id') if response.data else None
                return True, f"群聊消息发送成功 (ID: {message_id})"
            else:
                return False, f"群聊消息发送失败: {response.error_message}"
                
        except OneBotApiError as e:
            logger.error(f"发送群聊消息异常: {e}")
            return False, f"发送群聊消息异常: {e}"
    
    async def kick_group_member(self, group_id: Union[str, int], user_id: Union[str, int], 
                               reject_add_request: bool = False) -> Tuple[bool, str]:
        """踢出群成员
        
        Args:
            group_id: 群ID
            user_id: 用户ID
            reject_add_request: 是否拒绝此人的加群请求
            
        Returns:
            (成功状态, 响应消息)
        """
        try:
            data = {
                'group_id': int(group_id),
                'user_id': int(user_id),
                'reject_add_request': reject_add_request
            }
            
            response = await self._make_request('set_group_kick', data)
            
            if response.success:
                return True, f"成功踢出群成员 {user_id}"
            else:
                return False, f"踢出群成员失败: {response.error_message}"
                
        except OneBotApiError as e:
            logger.error(f"踢出群成员异常: {e}")
            return False, f"踢出群成员异常: {e}"
    
    async def get_group_member_list(self, group_id: Union[str, int]) -> Tuple[bool, Union[List[Dict], str]]:
        """获取群成员列表
        
        Args:
            group_id: 群ID
            
        Returns:
            (成功状态, 成员列表或错误消息)
        """
        try:
            data = {
                'group_id': int(group_id)
            }
            
            response = await self._make_request('get_group_member_list', data)
            
            if response.success and response.data:
                # 提取用户ID列表
                member_list = []
                for member in response.data:
                    if isinstance(member, dict) and 'user_id' in member:
                        member_list.append({
                            'user_id': str(member['user_id']),
                            'nickname': member.get('nickname', ''),
                            'role': member.get('role', 'member')
                        })
                
                logger.info(f"获取群 {group_id} 成员列表成功，共 {len(member_list)} 人")
                return True, member_list
            else:
                error_msg = response.error_message or "获取群成员列表失败"
                return False, error_msg
                
        except OneBotApiError as e:
            logger.error(f"获取群成员列表异常: {e}")
            return False, f"获取群成员列表异常: {e}"
    
    async def get_group_info(self, group_id: Union[str, int]) -> Tuple[bool, Union[Dict, str]]:
        """获取群信息
        
        Args:
            group_id: 群ID
            
        Returns:
            (成功状态, 群信息或错误消息)
        """
        try:
            data = {
                'group_id': int(group_id)
            }
            
            response = await self._make_request('get_group_info', data)
            
            if response.success and response.data:
                return True, response.data
            else:
                error_msg = response.error_message or "获取群信息失败"
                return False, error_msg
                
        except OneBotApiError as e:
            logger.error(f"获取群信息异常: {e}")
            return False, f"获取群信息异常: {e}"
    
    async def get_user_info(self, user_id: Union[str, int]) -> Tuple[bool, Union[Dict, str]]:
        """获取用户信息
        
        Args:
            user_id: 用户ID
            
        Returns:
            (成功状态, 用户信息或错误消息)
        """
        try:
            data = {
                'user_id': int(user_id)
            }
            
            response = await self._make_request('get_stranger_info', data)
            
            if response.success and response.data:
                return True, response.data
            else:
                error_msg = response.error_message or "获取用户信息失败"
                return False, error_msg
                
        except OneBotApiError as e:
            logger.error(f"获取用户信息异常: {e}")
            return False, f"获取用户信息异常: {e}"
    
    async def test_connection(self) -> Tuple[bool, str]:
        """测试连接
        
        Returns:
            (连接状态, 状态消息)
        """
        try:
            # 使用get_status接口测试连接
            response = await self._make_request('get_status', {})
            
            if response.success:
                return True, "OneBot连接正常"
            else:
                return False, f"OneBot连接异常: {response.error_message}"
                
        except OneBotApiError as e:
            logger.error(f"测试OneBot连接异常: {e}")
            return False, f"OneBot连接异常: {e}"


def create_onebot_adapter(base_url: str, access_token: Optional[str] = None, **kwargs) -> OneBotAdapter:
    """创建OneBot适配器实例的便捷函数
    
    Args:
        base_url: OneBot服务器地址
        access_token: 访问令牌（可选）
        **kwargs: 其他配置参数
        
    Returns:
        OneBotAdapter实例
    """
    config = OneBotConfig(
        base_url=base_url,
        access_token=access_token,
        **kwargs
    )
    return OneBotAdapter(config)