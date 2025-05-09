from config.configvalidator import ConfigValidator
from client.client import Client
from utils.logger import logger
import asyncio
import json


async def main():
    try:
        logger.info("🚀 Запуск скрипта...\n")

        # Загрузка параметров
        logger.info("⚙️ Загрузка и валидация параметров...\n")
        validator = ConfigValidator("config/settings.json", "config/wallets.txt")
        settings, wallets = await validator.validate_config()

        with open("constants/networks_data.json", "r", encoding="utf-8") as file:
            networks_data = json.load(file)
        with open("constants/tokens.json", "r", encoding="utf-8") as file:
            tokens = json.load(file)
        network = networks_data[settings["network"]]
        token_addresses = tokens[settings["network"]]

        # Инициализация клиента
        client = Client(
            rpc_url=network["rpc_url"],
            chain_id=network["chain_id"],
            explorer_url=network["explorer_url"],
            multicall_address=network["multicall_address"]
        )
        wallets_checksum = await client.to_checksum_list(wallets)

        # Запуск фетча
        logger.info("⚙️ Получение балансов...\n")
        balances = await client.fetch_balances(token_addresses, wallets_checksum)
        if balances:
            for wallet, tokens in balances.items():
                formatted = ", ".join([f"{symbol}: {value:.4f}" for symbol, value in tokens.items()])
                print(f"{wallet} → {formatted}")
            logger.info("✅ Балансы успешно получены.\n")
        else:
            logger.error("❌ Ошибка при получении балансов.")
    except Exception as e:
        logger.error(f"Произошла ошибка в основном пути: {e}")


if __name__ == "__main__":
    asyncio.run(main())
