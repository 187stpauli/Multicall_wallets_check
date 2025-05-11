from client.client import Client
from utils.logger import logger


async def check_balance(client: Client, amount: float, token: str, from_network: dict):
    """
    Проверяет достаточность баланса для совершения операции.
    
    Args:
        client: Экземпляр клиента для взаимодействия с блокчейном
        amount: Сумма для проверки
        token: Символ токена (ETH или другой токен)
        from_network: Словарь с данными о сети
        
    Raises:
        SystemExit: Если недостаточно средств
    """
    # Проверка баланса
    native_balance = await client.get_native_balance()
    gas = await client.get_tx_fee()

    if token != "Native":
        # Получаем адрес токена
        token_address = from_network.get(f"{token.lower()}_address")
        if not token_address:
            logger.error(f"Адрес токена {token} не найден в конфигурации сети.")
            exit(1)
            
        balance = await client.get_erc20_balance(token_address)
        amount_wei = await client.to_wei_main(amount, token_address)
        
        if amount_wei > balance:
            logger.error(f"Недостаточно баланса {token}! Требуется: "
                         f"{await client.from_wei_main(amount_wei, token_address):.8f} "
                         f"фактический баланс: "
                         f"{await client.from_wei_main(balance, token_address):.8f}\n")
            exit(1)
        if gas > native_balance:
            logger.error(f"Недостаточно баланса для оплаты газа! Требуется: "
                         f"{await client.from_wei_main(gas):.8f} "
                         f"фактический баланс: {await client.from_wei_main(native_balance):.8f}\n")
            exit(1)
    else:
        amount_wei = await client.to_wei_main(amount)
        total_cost = amount_wei + gas
        if total_cost > native_balance:
            logger.error(f"Недостаточно баланса! Требуется: {await client.from_wei_main(total_cost):.8f}"
                         f" фактический баланс: {await client.from_wei_main(native_balance):.8f}\n")
            exit(1)
