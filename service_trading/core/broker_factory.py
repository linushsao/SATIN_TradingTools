# ==============================================================================
# service_trading/core/broker_factory.py
#
# Version: V1.1-000 (Multi-Adapter Support)
# 更新日期: 2025-12-13
# 描述:     券商工廠 (Broker Factory)。
#           [修正]: 支援根據 'enabled_adapters' 列表載入多個 Adapter 實例。
# ==============================================================================

import importlib
from typing import Dict, Optional
from service_trading.core.interfaces import IBrokerAdapter
from shared.logging_tool import info, error, warn

class BrokerFactory:
    """
    負責產生 Broker Adapter 實例的工廠類別。
    支援多券商並行載入。
    """
    
    @staticmethod
    def get_adapters(config: dict) -> Dict[str, IBrokerAdapter]:
        """
        載入 config['enabled_adapters'] 中指定的所有 Adapter。
        Returns:
            Dict[str, IBrokerAdapter]: { "shioaji": adapter_instance, "fubon": ... }
        """
        adapters_map = {}
        
        # 1. 取得啟用列表 (相容舊版 active_adapter)
        enabled_list = config.get('enabled_adapters', [])
        if not enabled_list and config.get('active_adapter'):
            enabled_list = [config.get('active_adapter')]
            
        adapters_registry = config.get('adapters', {})
        
        info(f"[BrokerFactory] Loading adapters: {enabled_list}")
        
        for adapter_name in enabled_list:
            adapter_conf = adapters_registry.get(adapter_name)
            if not adapter_conf:
                warn(f"[BrokerFactory] Config for adapter '{adapter_name}' not found. Skipping.")
                continue
                
            module_path = adapter_conf.get('module_path')
            class_name = adapter_conf.get('class_name')
            adapter_specific_config = adapter_conf.get('config', {})
            
            try:
                # 動態匯入
                module = importlib.import_module(module_path)
                adapter_class = getattr(module, class_name)
                
                # 檢查介面
                if not issubclass(adapter_class, IBrokerAdapter):
                    error(f"[BrokerFactory] {class_name} does not inherit from IBrokerAdapter.")
                    continue
                    
                # 實例化
                instance = adapter_class()
                instance.initialize(adapter_specific_config)
                
                adapters_map[adapter_name] = instance
                info(f"[BrokerFactory] Adapter '{adapter_name}' loaded successfully.")
                
            except Exception as e:
                error(f"[BrokerFactory] Failed to load '{adapter_name}': {e}")
                
        return adapters_map

    @staticmethod
    def get_adapter(config: dict) -> Optional[IBrokerAdapter]:
        """
        [Legacy Support] 取得單一 Adapter (相容舊程式碼)。
        回傳第一個載入成功的 Adapter。
        """
        adapters = BrokerFactory.get_adapters(config)
        if adapters:
            # Return the first one
            return list(adapters.values())[0]
        return None