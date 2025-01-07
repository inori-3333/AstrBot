import traceback
from astrbot.core.db import BaseDatabase
from astrbot import logger
from astrbot.core.provider.func_tool_manager import FuncCall
from typing import List
from ..register import register_provider_adapter
from astrbot.core.provider.entites import LLMResponse
from .openai_source import ProviderOpenAIOfficial

@register_provider_adapter("zhipu_chat_completion", "智浦 Chat Completion 提供商适配器")
class ProviderZhipu(ProviderOpenAIOfficial):
    def __init__(
        self, 
        provider_config: dict, 
        provider_settings: dict,
        db_helper: BaseDatabase, 
        persistant_history = True
    ) -> None:
        super().__init__(provider_config, provider_settings, db_helper, persistant_history)
    
    async def text_chat(
        self,
        prompt: str,
        session_id: str,
        image_urls: List[str]=None,
        func_tool: FuncCall=None,
        contexts=None,
        system_prompt=None,
        **kwargs
    ) -> LLMResponse: 
        new_record = await self.assemble_context(prompt, image_urls)
        context_query = []
        
        if not contexts:
            context_query = [*self.session_memory[session_id], new_record]
        else:
            context_query = [*contexts, new_record]
        
        model_cfgs: dict = self.provider_config.get("model_config", {})
        # glm-4v-flash 只支持一张图片
        model: str = model_cfgs.get("model", "")
        if model.lower() == 'glm-4v-flash' and image_urls and len(context_query) > 1:
            logger.debug("glm-4v-flash 只支持一张图片，将只保留最后一张图片")
            logger.debug(context_query)
            new_context_query_ = []
            for i in range(0, len(context_query) - 1, 2):
                if isinstance(context_query[i].get("content", ""), list):
                    continue
                new_context_query_.append(context_query[i])
                new_context_query_.append(context_query[i+1])
            new_context_query_.append(context_query[-1]) # 保留最后一条记录
            context_query = new_context_query_
            logger.debug(context_query)
            
        if system_prompt:
            context_query.insert(0, {"role": "system", "content": system_prompt})
            
        payloads = {
            "messages": context_query,
            **model_cfgs
        }
        llm_response = None
        try:
            llm_response = await self._query(payloads, func_tool)
        except Exception as e:
            if "maximum context length" in str(e):
                logger.warning(f"请求失败：{e}。上下文长度超过限制。尝试弹出最早的记录然后重试。")
                self.pop_record(session_id)
            logger.warning(traceback.format_exc())
            
        await self.save_history(contexts, new_record, session_id, llm_response)

        return llm_response