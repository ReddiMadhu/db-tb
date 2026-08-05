import os
from app.core.config import settings

USE_LLM_CACHE = settings.USE_LLM_CACHE
# Prevent indefinite hangs on Azure/OpenAI (seen on live calc translate/judge).
LLM_REQUEST_TIMEOUT_SEC = float(os.getenv("LLM_REQUEST_TIMEOUT_SEC", "45"))


def get_llm(temperature: float = 0.1):
    """
    Returns an instance of ChatOpenAI or AzureChatOpenAI based on configuration.
    Returns None if no API key is configured.
    """
    llm = None
    openai_api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    azure_api_key = settings.AZURE_OPENAI_API_KEY or os.getenv("AZURE_OPENAI_API_KEY")
    timeout = LLM_REQUEST_TIMEOUT_SEC

    if azure_api_key:
        azure_endpoint = settings.AZURE_OPENAI_ENDPOINT or os.getenv("AZURE_OPENAI_ENDPOINT")
        if azure_endpoint and ("services.ai.azure.com" in azure_endpoint or "models.ai.azure.com" in azure_endpoint):
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                api_key=azure_api_key,
                base_url=azure_endpoint,
                model=settings.AZURE_OPENAI_DEPLOYMENT,
                temperature=temperature,
                default_headers={"api-key": azure_api_key},
                timeout=timeout,
                max_retries=1,
            )
        else:
            from langchain_openai import AzureChatOpenAI
            llm = AzureChatOpenAI(
                api_key=azure_api_key,
                azure_endpoint=azure_endpoint,
                azure_deployment=settings.AZURE_OPENAI_DEPLOYMENT,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                temperature=temperature,
                timeout=timeout,
                max_retries=1,
            )
    elif openai_api_key:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            api_key=openai_api_key,
            model=settings.OPENAI_MODEL,
            temperature=temperature,
            timeout=timeout,
            max_retries=1,
        )

    if llm and USE_LLM_CACHE:
        from app.core.cache import CachedLLM
        return CachedLLM(llm)

    return llm
