"""
Controle de lâmpadas/tomadas inteligentes TP-Link Tapo/Kasa — 100% via
rede local, sem depender de nuvem pra funcionar no dia a dia (só a
configuração inicial dos dispositivos, pelo app oficial, usa internet).

⚠️ NÃO TESTADO COM DISPOSITIVO DE VERDADE: escrito com base na
documentação do python-kasa, mas sem nenhum hardware físico disponível
pra testar durante o desenvolvimento. O primeiro teste real só acontece
quando você tiver um dispositivo Tapo/Kasa na sua rede.

Suporta MÚLTIPLOS dispositivos, cada um com nome próprio (ex: "luz da
sala", "tomada do abajur") — não é mais só uma lâmpada fixa.

Pré-requisito:
1. Compre um dispositivo Tapo (ex: L510, L530, P110) ou Kasa (ex: KL110, KL130)
2. Configure ele pelo app oficial (Tapo ou Kasa Smart) — só nessa etapa
   inicial precisa de internet/conta, pra parear com o Wi-Fi
3. Cadastre o dispositivo pelo JARVIS (`cadastrar_dispositivo_casa`) ou
   pela tela de Configurar, com o IP dele na rede local
"""

import asyncio
import json
import os
from pathlib import Path

TAPO_USERNAME = os.environ.get("TAPO_USERNAME", "")
TAPO_PASSWORD = os.environ.get("TAPO_PASSWORD", "")
TAPO_BULB_IP = os.environ.get("TAPO_BULB_IP", "")  # config antiga, de quando só existia 1 dispositivo — mantida por compatibilidade

DEVICES_CONFIG_PATH = Path(__file__).parent.parent / "devices_config.json"


def is_configured() -> bool:
    """As credenciais (usuário/senha) precisam existir — o IP agora é por dispositivo, não fixo."""
    return bool(TAPO_USERNAME and TAPO_PASSWORD)


def load_devices() -> list[dict]:
    """Lista de dispositivos cadastrados — inclui automaticamente a lâmpada antiga (TAPO_BULB_IP) se ela existir e ainda não tiver sido migrada."""
    dispositivos = []
    if DEVICES_CONFIG_PATH.exists():
        with open(DEVICES_CONFIG_PATH, encoding="utf-8") as f:
            dispositivos = json.load(f)

    # Compatibilidade: quem já tinha só TAPO_BULB_IP configurado (config antiga)
    # continua funcionando, aparecendo como "Luz principal" automaticamente.
    if TAPO_BULB_IP and not any(d["ip"] == TAPO_BULB_IP for d in dispositivos):
        dispositivos = [{"nome": "Luz principal", "ip": TAPO_BULB_IP}] + dispositivos

    return dispositivos


def save_devices(dispositivos: list[dict]) -> None:
    with open(DEVICES_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(dispositivos, f, ensure_ascii=False, indent=2)


def add_device(nome: str, ip: str) -> None:
    dispositivos = [d for d in load_devices() if d["ip"] != TAPO_BULB_IP]  # não duplica a config antiga
    dispositivos = [d for d in dispositivos if d["nome"].lower() != nome.lower()]
    dispositivos.append({"nome": nome, "ip": ip})
    save_devices(dispositivos)


def remove_device(nome: str) -> bool:
    dispositivos = load_devices()
    novos = [d for d in dispositivos if d["nome"].lower() != nome.lower()]
    if len(novos) == len(dispositivos):
        return False
    save_devices(novos)
    return True


def _find_device_ip(nome: str) -> str | None:
    dispositivos = load_devices()
    for d in dispositivos:
        if d["nome"].lower() == nome.lower():
            return d["ip"]
    # Se só tiver 1 dispositivo cadastrado, aceita qualquer nome (comodidade pra quem só tem 1)
    if len(dispositivos) == 1:
        return dispositivos[0]["ip"]
    return None


async def _get_device(ip: str):
    from kasa import Discover

    device = await Discover.discover_single(ip, username=TAPO_USERNAME, password=TAPO_PASSWORD)
    await device.update()
    return device


def turn_on(nome: str = "") -> str:
    if not is_configured():
        return "Casa inteligente não configurada. Preencha TAPO_USERNAME e TAPO_PASSWORD no .env."
    ip = _find_device_ip(nome) if nome else (load_devices()[0]["ip"] if load_devices() else None)
    if not ip:
        return f"Dispositivo '{nome}' não encontrado. Use `listar_dispositivos_casa` pra ver os cadastrados."
    try:
        return asyncio.run(_turn_on_async(ip))
    except Exception as e:
        return f"Erro ao ligar: {e}"


async def _turn_on_async(ip: str) -> str:
    device = await _get_device(ip)
    await device.turn_on()
    return "Ligado."


def turn_off(nome: str = "") -> str:
    if not is_configured():
        return "Casa inteligente não configurada. Preencha TAPO_USERNAME e TAPO_PASSWORD no .env."
    ip = _find_device_ip(nome) if nome else (load_devices()[0]["ip"] if load_devices() else None)
    if not ip:
        return f"Dispositivo '{nome}' não encontrado. Use `listar_dispositivos_casa` pra ver os cadastrados."
    try:
        return asyncio.run(_turn_off_async(ip))
    except Exception as e:
        return f"Erro ao desligar: {e}"


async def _turn_off_async(ip: str) -> str:
    device = await _get_device(ip)
    await device.turn_off()
    return "Desligado."


def set_brightness(percent: int, nome: str = "") -> str:
    if not is_configured():
        return "Casa inteligente não configurada. Preencha TAPO_USERNAME e TAPO_PASSWORD no .env."
    ip = _find_device_ip(nome) if nome else (load_devices()[0]["ip"] if load_devices() else None)
    if not ip:
        return f"Dispositivo '{nome}' não encontrado. Use `listar_dispositivos_casa` pra ver os cadastrados."
    percent = max(1, min(100, percent))
    try:
        return asyncio.run(_set_brightness_async(ip, percent))
    except Exception as e:
        return f"Erro ao ajustar o brilho: {e}"


async def _set_brightness_async(ip: str, percent: int) -> str:
    from kasa import Module

    device = await _get_device(ip)
    light = device.modules.get(Module.Light)
    if light is None:
        return "Esse dispositivo não suporta ajuste de brilho (não tem o módulo Light)."
    await light.set_brightness(percent)
    return f"Brilho ajustado pra {percent}%."
