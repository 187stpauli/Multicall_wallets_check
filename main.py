from config.configvalidator import ConfigValidator
from client.client import Client
from modules.bridge import Bridge
from utils.logger import logger
import asyncio
import json

with open("abi/multicall_abi.json", "r", encoding="utf-8") as f:
    MULTICALL_ABI = json.load(f)


async def main():
    try:
        logger.info("🚀 Запуск скрипта...\n")
        # Загрузка параметров
        logger.info("⚙️ Загрузка и валидация параметров...\n")
        validator = ConfigValidator("config/settings.json", "config/wallets.txt")
        settings, wallets = await validator.validate_config()

        with open("constants/networks_data.json", "r", encoding="utf-8") as file:
            networks_data = json.load(file)

        network = networks_data[settings["network"]]

        # Инициализация клиента
        client = Client(
            rpc_url=network["rpc_url"],
            chain_id=network["chain_id"],
            explorer_url=network["explorer_url"],
            multicall_address=network["multicall_address"]
        )
        balance_calls = []

        balance_call = token_contract.encode_abi(
            fn_name="",
            args=([
                ""
            ])
        )
        balance_calls.append([
            123
        ])
        real_amount = 0
        if settings["token"] == "USDC":
            real_amount = await client.to_wei_main(client.amount, from_network['usdc_address'])
        elif settings["token"] == "ETH":
            real_amount = await client.to_wei_main(client.amount)
        await client.set_amount(real_amount)

        # Запуск бриджа
        logger.info("⚙️ Собираем и подписываем транзакцию...\n")
        bridge = await Bridge.create(client, from_network, to_network, settings, pool_abi)
        await bridge.execute_bridge()

    except Exception as e:
        logger.error(f"Произошла ошибка в основном пути: {e}")


if __name__ == "__main__":
    asyncio.run(main())
