import logging
import json
import re

logger = logging.getLogger(__name__)


class ConfigValidator:
    def __init__(self, config_path: str, wallets_path: str):
        self.config_path = config_path
        self.wallets_path = wallets_path
        self.config_data = self.load_config()
        self.wallets = self.load_wallets()

    def load_wallets(self) -> list:
        """Загружает конфигурационный файл"""
        try:
            with open(self.wallets_path, "r", encoding="utf-8") as file:
                lines = file.readlines()
                wallets = [line.strip() for line in lines]
                return wallets
        except FileNotFoundError:
            logging.error(f"❗️ Файл конфигурации {self.config_path} не найден.")
            exit(1)

    def load_config(self) -> dict:
        """Загружает конфигурационный файл"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            logging.error(f"❗️ Файл конфигурации {self.config_path} не найден.")
            exit(1)
        except json.JSONDecodeError:
            logging.error(f"❗️ Ошибка разбора JSON в файле конфигурации {self.config_path}.")
            exit(1)

    async def validate_config(self) -> tuple[dict, list]:
        """Валидация всех полей конфигурации"""

        await self.validate_required_keys()

        if "network" not in self.config_data:
            logging.error("❗️ Ошибка: Отсутствует 'network' в конфигурации.")
            exit(1)

        await self.validate_network(self.config_data["network"])
        await self.validate_wallets(self.wallets)
        return self.config_data, self.wallets

    async def validate_required_keys(self):
        required_keys = [
            "network"
        ]

        for key in required_keys:
            if key not in self.config_data:
                logging.error(f"❗️ Ошибка: отсутствует обязательный ключ '{key}' в settings.json")
                exit(1)

    @staticmethod
    async def validate_network(network: str) -> None:
        """Валидация названия сети"""
        networks = [
            "Base",
            "Arbitrum",
            "Optimism"
        ]
        if network not in networks:
            logging.error("❗️ Ошибка: Неподдерживаемая сеть! Введите одну из поддерживаемых сетей.")
            exit(1)

    @staticmethod
    async def validate_wallets(wallets: list) -> None:
        """Валидация кошельков в списке"""

        if not wallets:
            logging.error("❗️ Файл с кошельками пуст.")
            exit(1)

        # Проверяем каждый кошелек
        for wallet in wallets:
            if not wallet:
                logging.error("❗️ Найдена пустая строка в файле с кошельками.")
                exit(1)

            if not wallet.startswith("0x") or len(wallet) != 42:
                logging.error(f"❗️ Некорректный адрес кошелька: {wallet}")
                exit(1)

            if not re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet):
                logging.error(f"❗️ Адрес кошелька содержит недопустимые символы: {wallet}")
                exit(1)
