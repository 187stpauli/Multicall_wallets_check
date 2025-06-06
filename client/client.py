from eth_abi import decode_single
from eth_utils import to_checksum_address
from rlp import DecodingError
from web3.middleware.geth_poa import async_geth_poa_middleware
from web3.exceptions import TransactionNotFound, ContractLogicError, BadFunctionCallOutput
from web3 import AsyncWeb3, AsyncHTTPProvider
from web3.contract import AsyncContract
from typing import Optional, Union, List, Dict
from web3.types import TxParams
from hexbytes import HexBytes
from client.networks import Network
import asyncio
import logging
import json

with open("abi/multicall_abi.json", "r", encoding="utf-8") as f:
    MULTICALL_ABI = json.load(f)

with open("abi/erc20_abi.json", "r", encoding="utf-8") as file:
    ERC20_ABI = json.load(file)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)


class Client:
    def __init__(self, multicall_address: str, chain_id: int, rpc_url: str, explorer_url: str):
        self.explorer_url = explorer_url
        self.multicall_address = multicall_address
        self.chain_id = chain_id
        self.rpc_url = rpc_url

        # Определяем сеть
        if isinstance(chain_id, str):
            self.network = Network.from_name(chain_id)
        else:
            self.network = Network.from_chain_id(chain_id)

        self.chain_id = self.network.chain_id

        # Инициализация AsyncWeb3
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        # Применяем middleware для PoA-сетей
        if self.network.is_poa:
            self.w3.middleware_onion.clear()
            self.w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)

        self.eip_1559 = True

    # Получение баланса нативного токена
    async def get_native_balance(self, address: str) -> float:
        """Получает баланс нативного токена в ETH/BNB/MATIC и т.д."""
        address = to_checksum_address(address)
        balance_wei = await self.w3.eth.get_balance(address)
        return balance_wei

    async def to_checksum_list(self, addresses: list[str]) -> list[str]:
        checksummed = []
        for addr in addresses:
            if isinstance(addr, str) and addr.startswith("0x") and len(addr) == 42:
                try:
                    checksummed.append(self.w3.to_checksum_address(addr))
                except ValueError:
                    continue  # пропускаем если адрес некорректен
        return checksummed

    async def fetch_balances(self, token_addresses: dict[str, str],
                             wallets: List[str]) -> Dict[str, Dict[str, float]] | None:
        try:
            multicall_address = to_checksum_address(self.multicall_address)
            multicall = self.w3.eth.contract(address=multicall_address, abi=MULTICALL_ABI)

            calls = []
            token_symbols = list(token_addresses.keys())

            for symbol, addr in token_addresses.items():
                contract = self.w3.eth.contract(address=to_checksum_address(addr), abi=ERC20_ABI)
                for wallet in wallets:
                    data = contract.encodeABI(fn_name="balanceOf", args=[wallet])
                    calls.append((addr, data))

            multicall_inputs = [
                {
                    "target": to_checksum_address(target),
                    "callData": data
                } for target, data in calls
            ]

            results = await multicall.functions.tryAggregate(False, multicall_inputs).call()

            # Словарь: {wallet: {token: balance}}
            output = {wallet: {} for wallet in wallets}
            idx = 0
            for symbol in token_symbols:
                token_address = token_addresses[symbol]
                for wallet in wallets:
                    success, return_data = results[idx]
                    raw_balance = decode_single('uint256', return_data) if success else 0
                    human_balance = await self.from_wei_main(raw_balance, token_address)
                    output[wallet][symbol] = human_balance
                    idx += 1

            # Добавляем нативные балансы
            for wallet in wallets:
                balance_wei = await self.w3.eth.get_balance(to_checksum_address(wallet))
                output[wallet]["Native"] = await self.from_wei_main(balance_wei)

            return output

        except (ValueError, DecodingError, ContractLogicError, BadFunctionCallOutput) as e:
            logger.error(f"❗ Ошибка при получении балансов: {e}")
            return None
        except Exception as e:
            logger.error(f"❗ Неизвестная ошибка: {e}")
            return None

    # Получение баланса ERC20
    async def get_erc20_balance(self, address: str) -> float | int:

        contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(address), abi=ERC20_ABI)
        try:
            balance = await contract.functions.balanceOf(address).call()
            return balance
        except Exception as e:
            logger.error(f"❌ Ошибка при получении баланса ERC20: {e}")
            return 0

    async def get_allowance(self, token_address: str, owner: str, spender: str) -> int:
        try:
            contract = await self.get_contract(token_address, ERC20_ABI)
            allowance = await contract.functions.allowance(
                self.w3.to_checksum_address(owner),
                self.w3.to_checksum_address(spender)
            ).call()
            return allowance
        except Exception as e:
            logger.error(f"❌ Ошибка при получении allowance: {e}")
            return 0

    # Создание объекта контракт для дальнейшего обращения к нему
    async def get_contract(self, contract_address: str, abi: list) -> AsyncContract:
        return self.w3.eth.contract(
            address=self.w3.to_checksum_address(contract_address), abi=abi
        )

    # Получение суммы газа за транзакцию
    async def get_tx_fee(self) -> int:
        try:
            fee_history = await self.w3.eth.fee_history(10, "latest", [50])
            base_fee = fee_history['baseFeePerGas'][-1]
            max_priority_fee = await self.w3.eth.max_priority_fee
            estimated_gas = 70_000
            max_fee_per_gas = (base_fee + max_priority_fee) * estimated_gas

            return max_fee_per_gas
        except Exception as e:
            logger.warning(f"Ошибка при расчёте комиссии, используем fallback: {e}")
            fallback_gas_price = await self.w3.eth.gas_price
            return fallback_gas_price * 70_000

    # Преобразование в веи
    async def to_wei_main(self, number: int | float, token_address: Optional[str] = None):
        if token_address:
            contract = await self.get_contract(token_address, ERC20_ABI)
            decimals = await contract.functions.decimals().call()
        else:
            decimals = 18

        unit_name = {
            6: "mwei",
            9: "gwei",
            18: "ether"
        }.get(decimals)

        if not unit_name:
            raise RuntimeError(f"Невозможно найти имя юнита с децималами: {decimals}")
        return self.w3.to_wei(number, unit_name)

    # Преобразование из веи
    async def from_wei_main(self, number: int | float, token_address: Optional[str] = None):
        if token_address:
            contract = await self.get_contract(token_address, ERC20_ABI)
            decimals = await contract.functions.decimals().call()
        else:
            decimals = 18

        unit_name = {
            6: "mwei",
            9: "gwei",
            18: "ether"
        }.get(decimals)

        if not unit_name:
            raise RuntimeError(f"Невозможно найти имя юнита с децималами: {decimals}")
        return self.w3.from_wei(number, unit_name)

    # Approve
    async def approve_usdc(self, usdc_address, spender, amount, eip_1559: bool):
        contract = await self.get_contract(usdc_address, ERC20_ABI)
        owner = self.address
        nonce = await self.w3.eth.get_transaction_count(owner)
        chain_id = await self.w3.eth.chain_id

        tx_params = {
            'from': owner,
            'nonce': nonce,
            'gas': 300_000,
            'chainId': chain_id
        }

        if eip_1559:
            base_fee = await self.w3.eth.gas_price
            max_priority_fee = int(base_fee * 0.1) or 1_000_000  # Минимальная чаевая
            max_fee = int(base_fee * 1.5 + max_priority_fee)

            tx_params.update({
                'maxPriorityFeePerGas': max_priority_fee,
                'maxFeePerGas': max_fee,
                'type': '0x2'
            })
        else:
            tx_params['gasPrice'] = int(await self.w3.eth.gas_price * 1.25)

        # Формирование транзакции approve
        tx = await contract.functions.approve(spender, amount).build_transaction(tx_params)

        # Подпись и отправка
        signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash)

        return receipt

    # Подготовка транзакции
    async def prepare_tx(self, value: Union[int, float] = 0) -> TxParams:
        transaction: TxParams = {
            "chainId": await self.w3.eth.chain_id,
            "nonce": await self.w3.eth.get_transaction_count(self.address),
            "from": self.address,
            "value": value,
        }

        if self.eip_1559:
            base_fee = await self.w3.eth.gas_price
            max_priority_fee_per_gas = await self.w3.eth.max_priority_fee or base_fee
            max_fee_per_gas = int(base_fee * 1.25 + max_priority_fee_per_gas)

            transaction.update({
                "maxPriorityFeePerGas": max_priority_fee_per_gas,
                "maxFeePerGas": max_fee_per_gas,
                "type": "0x2",
            })
        else:
            transaction["gasPrice"] = int((await self.w3.eth.gas_price) * 1.25)

        return transaction

    # Подпись и отправка транзакции
    async def sign_and_send_tx(self, transaction: TxParams, without_gas: bool = False,
                               external_gas: Optional[int] = None):
        try:

            if not without_gas:
                if external_gas:
                    transaction["gas"] = int(external_gas * 1.5)
                else:
                    transaction["gas"] = int((await self.w3.eth.estimate_gas(transaction)) * 1.5)
            nonce = await self.w3.eth.get_transaction_count(self.address)
            transaction['nonce'] = nonce
            signed = self.w3.eth.account.sign_transaction(transaction, self.private_key)
            signed_raw_tx = signed.raw_transaction
            logger.info("✅ Транзакция подписана\n")

            tx_hash_bytes = await self.w3.eth.send_raw_transaction(signed_raw_tx)
            tx_hash_hex = self.w3.to_hex(tx_hash_bytes)
            logger.info("✅ Транзакция отправлена: %s\n", tx_hash_hex)

            return tx_hash_hex
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке транзакции: {e}")
            return None

    # Ожидание результата транзакции
    async def wait_tx(self, tx_hash: Union[str, HexBytes], explorer_url: Optional[str] = None) -> bool:
        total_time = 0
        timeout = 120
        poll_latency = 10

        tx_hash_bytes = HexBytes(tx_hash)  # Приведение к HexBytes

        while True:
            try:
                receipt = await self.w3.eth.get_transaction_receipt(tx_hash_bytes)
                status = receipt.get("status")
                if status == 1:
                    logger.info(f"✅ Транзакция выполнена успешно: {explorer_url}/tx/{tx_hash_bytes.hex()}\n")
                    return True
                elif status is None:
                    await asyncio.sleep(poll_latency)
                else:
                    logger.error(f"❌ Транзакция не выполнена: {explorer_url}/tx/{tx_hash_bytes.hex()}")
                    return False
            except TransactionNotFound:
                if total_time > timeout:
                    logger.warning(f"❌ Транзакция {tx_hash_bytes.hex()} не подтвердилась за 120 секунд")
                    return False
                total_time += poll_latency
                await asyncio.sleep(poll_latency)
            except Exception as e:
                logger.error(f"❌ Ошибка при получении receipt: {e}")
                return False
