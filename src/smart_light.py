"""
Controle de lâmpadas inteligentes TP-Link Tapo/Kasa — 100% via rede local,
sem depender de nuvem pra funcionar no dia a dia (só a configuração inicial
das lâmpadas, pelo app oficial, usa internet).

⚠️ NÃO TESTADO COM LÂMPADA DE VERDADE: escrito com base na documentação do
python-kasa, mas sem nenhum hardware físico disponível pra testar durante o
desenvolvimento. O primeiro teste real só acontece quando você tiver uma
lâmpada Tapo/Kasa na sua rede.

Pré-requisito:
1. Compre uma lâmpada Tapo (ex: L510, L530) ou Kasa (ex: KL110, KL130)
2. Configure ela pelo app oficial (Tapo ou Kasa Smart) — só nessa etapa
   inicial precisa de internet/conta, pra parear com o Wi-Fi
3. Preencha as credenciais e o IP da lâmpada no .env (veja README)
"""

import asyncio
import os

TAPO_USERNAME = os.environ.get("TAPO_USERNAME", "")
TAPO_PASSWORD = os.environ.get("TAPO_PASSWORD", "")
TAPO_BULB_IP = os.environ.get("TAPO_BULB_IP", "")


def is_configured() -> bool:
    return bool(TAPO_USERNAME and TAPO_PASSWORD and TAPO_BULB_IP)


async def _get_device():
    from kasa import Discover

    device = await Discover.discover_single(
        TAPO_BULB_IP, username=TAPO_USERNAME, password=TAPO_PASSWORD
    )
    await device.update()
    return device


def turn_on() -> str:
    if not is_configured():
        return "Lâmpada não configurada. Preencha TAPO_USERNAME, TAPO_PASSWORD e TAPO_BULB_IP no .env."
    try:
        return asyncio.run(_turn_on_async())
    except Exception as e:
        return f"Erro ao ligar a lâmpada: {e}"


async def _turn_on_async() -> str:
    device = await _get_device()
    await device.turn_on()
    return "Lâmpada ligada."


def turn_off() -> str:
    if not is_configured():
        return "Lâmpada não configurada. Preencha TAPO_USERNAME, TAPO_PASSWORD e TAPO_BULB_IP no .env."
    try:
        return asyncio.run(_turn_off_async())
    except Exception as e:
        return f"Erro ao desligar a lâmpada: {e}"


async def _turn_off_async() -> str:
    device = await _get_device()
    await device.turn_off()
    return "Lâmpada desligada."


def set_brightness(percent: int) -> str:
    if not is_configured():
        return "Lâmpada não configurada. Preencha TAPO_USERNAME, TAPO_PASSWORD e TAPO_BULB_IP no .env."
    percent = max(1, min(100, percent))
    try:
        return asyncio.run(_set_brightness_async(percent))
    except Exception as e:
        return f"Erro ao ajustar o brilho: {e}"


async def _set_brightness_async(percent: int) -> str:
    from kasa import Module

    device = await _get_device()
    light = device.modules.get(Module.Light)
    if light is None:
        return "Essa lâmpada não suporta ajuste de brilho (não tem o módulo Light)."
    await light.set_brightness(percent)
    return f"Brilho ajustado pra {percent}%."
