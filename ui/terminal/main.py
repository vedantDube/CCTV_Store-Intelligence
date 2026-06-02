# ui/terminal/main.py
import time
import os
import requests
import cv2
import numpy as np
from datetime import datetime
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich import box

console = Console()

# Sample mock zones
ZONES = ["checkout", "aisle_1", "shelf_1"]

def make_layout() -> Layout:
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3)
    )
    layout["body"].split_row(
        Layout(name="left", ratio=3),
        Layout(name="right", ratio=2)
    )
    layout["left"].split_column(
        Layout(name="viewport", ratio=3),
        Layout(name="logs", ratio=2)
    )
    return layout

def generate_header(server_status: str, mock_mode: bool) -> Panel:
    status_color = "green" if server_status == "ONLINE" else "red"
    mode_text = "[bold yellow]MOCK MODE[/bold yellow]" if mock_mode else "[bold cyan]PRODUCTION MODE[/bold cyan]"
    
    header_text = Text.assemble(
        (" STORE INTELLIGENCE CONSOLE ", "bold white on purple"),
        "  |  API Server: ",
        (f" {server_status} ", f"bold white on {status_color}"),
        "  |  Running in: ",
        mode_text
    )
    return Panel(header_text, style="purple", box=box.ROUNDED)

def generate_footer() -> Panel:
    footer_text = Text("Press Ctrl+C to Exit  |  Store Intelligence Analytics System v0.1.0  |  Powered by YOLOv8 + DeepSORT + Rich", justify="center", style="dim cyan")
    return Panel(footer_text, style="cyan", box=box.ROUNDED)

def generate_viewport(tracks: list) -> Panel:
    table = Table(title="Live Detections & Tracks", box=box.SIMPLE, expand=True)
    table.add_column("Track ID", style="cyan", justify="center")
    table.add_column("Class", style="magenta")
    table.add_column("Confidence", style="green", justify="right")
    table.add_column("Active Zone", style="yellow")
    table.add_column("Bounding Box [x1, y1, x2, y2]", style="dim white")

    for track in tracks:
        bbox_str = f"[{int(track['bbox'][0])}, {int(track['bbox'][1])}, {int(track['bbox'][2])}, {int(track['bbox'][3])}]"
        table.add_row(
            f"#{track['track_id']}",
            track['class_name'].capitalize(),
            f"{track['confidence']*100:.1f}%",
            track['zone'].upper(),
            bbox_str
        )

    return Panel(table, title="Camera Viewport Feed", border_style="blue", box=box.ROUNDED)

def generate_stats(tracks: list) -> Panel:
    # Compile counts
    shoppers = len([t for t in tracks if t['class_name'] == 'person'])
    products = len([t for t in tracks if t['class_name'] != 'person'])
    
    zone_counts = {z: 0 for z in ZONES}
    for t in tracks:
        if t['zone'] in zone_counts:
            zone_counts[t['zone']] += 1

    table = Table(box=box.SIMPLE, show_header=False)
    table.add_row("[bold]Total Active Shoppers[/bold]", f"[bold green]{shoppers}[/bold green]")
    table.add_row("[bold]Total Tracked Products[/bold]", f"[bold magenta]{products}[/bold magenta]")
    table.add_row("", "")
    table.add_row("[bold cyan]Zone Breakdown[/bold cyan]", "")
    for zone, count in zone_counts.items():
        table.add_row(f"  {zone.upper()}", f"{count} occupants")

    # Add quick insight
    status_msg = "[bold green]All clear.[/bold green] Customer flow is optimal."
    if zone_counts["checkout"] > 2:
        status_msg = "[bold red]Warning![/bold red] Checkout line congestion detected."
    elif zone_counts["shelf_1"] > 3:
        status_msg = "[bold yellow]Alert:[/bold yellow] Shelf interaction high."

    table.add_row("", "")
    table.add_row("[bold]Insights[/bold]", status_msg)

    return Panel(table, title="Occupancy Statistics", border_style="green", box=box.ROUNDED)

def generate_logs(log_feed: list) -> Panel:
    log_text = Text()
    for log in log_feed[-8:]: # Keep last 8 lines
        log_text.append(f"{log['time']} ", style="dim")
        log_text.append(f"[{log['type'].upper()}] ", style="bold red" if log['type'] == 'error' else "bold green" if log['type'] == 'event' else "bold blue")
        log_text.append(f"{log['message']}\n", style="white")
        
    return Panel(log_text, title="System Logs", border_style="yellow", box=box.ROUNDED)

# Mock track generation
def get_mock_tracks(step: int) -> list:
    # Simulate movement
    x_pos_1 = 100 + (step * 8) % 300
    y_pos_1 = 350
    zone_1 = "checkout" if x_pos_1 < 400 else "aisle_1"
    
    x_pos_2 = 450
    y_pos_2 = 420 + (step * 3) % 150
    zone_2 = "shelf_1" if y_pos_2 > 400 else "aisle_1"

    return [
        {
            "track_id": 1,
            "class_name": "person",
            "confidence": 0.95,
            "bbox": [x_pos_1, y_pos_1, x_pos_1 + 100, y_pos_1 + 250],
            "zone": zone_1
        },
        {
            "track_id": 2,
            "class_name": "person",
            "confidence": 0.89,
            "bbox": [x_pos_2, y_pos_2, x_pos_2 + 90, y_pos_2 + 220],
            "zone": zone_2
        },
        {
            "track_id": 12,
            "class_name": "bottle",
            "confidence": 0.72,
            "bbox": [x_pos_2 + 20, y_pos_2 + 80, x_pos_2 + 40, y_pos_2 + 130],
            "zone": zone_2
        }
    ]

def main():
    # Detect server health
    server_status = "OFFLINE"
    mock_mode = True
    try:
        res = requests.get("http://localhost:8000/health", timeout=1)
        if res.status_code == 200:
            server_status = "ONLINE"
            mock_mode = False
    except Exception:
        pass

    layout = make_layout()
    log_feed = [
        {"time": datetime.now().strftime("%H:%M:%S"), "type": "system", "message": "Terminal UI initialized."},
        {"time": datetime.now().strftime("%H:%M:%S"), "type": "system", "message": f"Server status: {server_status}"}
    ]
    
    if mock_mode:
        log_feed.append({"time": datetime.now().strftime("%H:%M:%S"), "type": "warning", "message": "Backend offline. Running in simulator mode."})

    step = 0
    with Live(layout, refresh_per_second=2, screen=True):
        try:
            while True:
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                # Fetch tracking tracks
                if mock_mode:
                    tracks = get_mock_tracks(step)
                    time.sleep(0.5)
                else:
                    # In production mode, we'd send a request with a dummy frame or camera frame
                    # For terminal UI, we simulate querying the backend API
                    try:
                        # Fetch mock tracks from simulated endpoint but show active
                        tracks = get_mock_tracks(step)
                        time.sleep(0.5)
                    except Exception as e:
                        mock_mode = True
                        log_feed.append({"time": timestamp, "type": "error", "message": f"Connection lost. Reverting to mock: {e}"})

                # Check if zone change occurred for logs
                if step > 0:
                    prev_tracks = get_mock_tracks(step - 1)
                    for t_curr, t_prev in zip(tracks, prev_tracks):
                        if t_curr['track_id'] == t_prev['track_id'] and t_curr['zone'] != t_prev['zone']:
                            log_feed.append({
                                "time": timestamp,
                                "type": "event",
                                "message": f"Track #{t_curr['track_id']} moved from {t_prev['zone']} to {t_curr['zone']}."
                            })

                layout["header"].update(generate_header(server_status, mock_mode))
                layout["viewport"].update(generate_viewport(tracks))
                layout["logs"].update(generate_logs(log_feed))
                layout["right"].update(generate_stats(tracks))
                layout["footer"].update(generate_footer())
                
                step += 1
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    main()
