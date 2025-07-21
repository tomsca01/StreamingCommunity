# 16.03.25

import os
import re


# External library
import httpx
from bs4 import BeautifulSoup
from rich.console import Console


# Internal utilities
from StreamingCommunity.Util.os import os_manager
from StreamingCommunity.Util.message import start_message
from StreamingCommunity.Util.headers import get_headers
from StreamingCommunity.Util.config_json import config_manager
from StreamingCommunity.Lib.Downloader import HLS_Downloader
from StreamingCommunity.TelegramHelp.telegram_bot import get_bot_instance, TelegramSession


# Logic class
from StreamingCommunity.Api.Template.config_loader import site_constant
from StreamingCommunity.Api.Template.Class.SearchType import MediaItem


# Player
from StreamingCommunity.Api.Player.supervideo import VideoSource


# Variable
console = Console()
max_timeout = config_manager.get_int("REQUESTS", "timeout")


def download_film(select_title: MediaItem) -> str:
    """
    Downloads a film using the provided film ID, title name, and domain.

    Parameters:
        - select_title (MediaItem): The selected media item.

    Return:
        - str: output path if successful, otherwise None
    """
    if site_constant.TELEGRAM_BOT:
        bot = get_bot_instance()
        bot.send_message(f"Download in corso:\n{select_title.name}", None)

        # Viene usato per lo screen
        console.print(f"## Download: [red]{select_title.name} ##")

        # Get script_id
        script_id = TelegramSession.get_session()
        if script_id != "unknown":
            TelegramSession.updateScriptId(script_id, select_title.name)

    start_message()
    console.print(f"[bold yellow]Download:[/bold yellow] [red]{site_constant.SITE_NAME}[/red] → [cyan]{select_title.name}[/cyan] \n")
    
    # Extract mostraguarda URL
    try:
        response = httpx.get(select_title.url, headers=get_headers(), timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        iframes = soup.find_all('iframe')
        
        # Verifica se ci sono iframe trovati
        if not iframes:
            console.print(f"[red]Site: {site_constant.SITE_NAME}, error: No iframes found")
            return None
            
        mostraguarda = iframes[0]['src']
        
        # Gestisci URL relativi (che iniziano con //)
        if mostraguarda.startswith('//'):
            mostraguarda = f"https:{mostraguarda}"
        # Gestisci percorsi assoluti (che iniziano con /)
        elif mostraguarda.startswith('/'):
            # Estrai il dominio dall'URL originale
            domain_match = re.match(r'https?://([^/]+)', select_title.url)
            if domain_match:
                domain = domain_match.group(1)
                mostraguarda = f"https://{domain}{mostraguarda}"
            else:
                # Usa un dominio predefinito se non possiamo estrarre il dominio
                mostraguarda = f"https://mostraguarda.top{mostraguarda}"
        # Gestisci URL relativi (che non hanno schema)
        elif not mostraguarda.startswith('http://') and not mostraguarda.startswith('https://'):
            mostraguarda = f"https://{mostraguarda}"
            
        console.print(f"[cyan]Mostraguarda URL: [yellow]{mostraguarda}")
    
    except Exception as e:
        console.print(f"[red]Site: {site_constant.SITE_NAME}, request error: {e}, get mostraguarda")
        return None

    # Extract supervideo URL
    supervideo_url = None
    try:
        response = httpx.get(mostraguarda, headers=get_headers(), timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Prova diversi pattern per supervideo
        patterns = [
            r'//supervideo\.[^/]+/[a-z]/[a-zA-Z0-9]+',  # Pattern originale
            r'https?://supervideo\.[^/]+/[a-z]/[a-zA-Z0-9]+',  # Con protocollo
            r'supervideo\.[^/]+/[a-z]/[a-zA-Z0-9]+',  # Senza //
            r'//supervideo\.[^"\s]+',  # Pattern più generico
            r'https?://supervideo\.[^"\s]+',  # Pattern generico con protocollo
        ]
        
        supervideo_match = None
        for pattern in patterns:
            supervideo_match = re.search(pattern, response.text)
            if supervideo_match:
                console.print(f"[green]Found supervideo URL with pattern: {pattern}")
                break
        
        if supervideo_match:
            supervideo_url = supervideo_match.group(0)
            # Aggiungi https: se necessario
            if supervideo_url.startswith('//'):
                supervideo_url = 'https:' + supervideo_url
            elif not supervideo_url.startswith('http'):
                supervideo_url = 'https://' + supervideo_url
                
            console.print(f"[cyan]Supervideo URL: [yellow]{supervideo_url}")
        else:
            console.print(f"[yellow]⚠️  Contenuto non disponibile")
            console.print(f"Il film \"{select_title.name}\" non è attualmente disponibile per il download.")
            return None

    except Exception as e:
        console.print(f"[red]Site: {site_constant.SITE_NAME}, request error: {e}, get supervideo URL")
        console.print("[yellow]This content will be available soon![/yellow]")
        return None
    
    # Init class
    video_source = VideoSource(supervideo_url)
    master_playlist = video_source.get_playlist()

    # Define the filename and path for the downloaded film
    title_name = os_manager.get_sanitize_file(select_title.name) + ".mp4"
    mp4_path = os.path.join(site_constant.MOVIE_FOLDER, title_name.replace(".mp4", ""))

    # Download the film using the m3u8 playlist, and output filename
    r_proc = HLS_Downloader(
        m3u8_url=master_playlist,
        output_path=os.path.join(mp4_path, title_name)
    ).start()

    if site_constant.TELEGRAM_BOT:

        # Delete script_id
        script_id = TelegramSession.get_session()
        if script_id != "unknown":
            TelegramSession.deleteScriptId(script_id)

    if r_proc['error'] is not None:
        try: os.remove(r_proc['path'])
        except: pass

    return r_proc['path']