import asyncio
import datetime
import time
import speedtest

from FileStream.utils.human_readable import humanbytes

MSG_SPEEDTEST_START = "🚀 Running Speed Test..."
MSG_SPEEDTEST_ERROR = (
    "❌ Speed Test Failed!\n"
    "> Unable to complete the speed test. Please try again later."
)

RESULT_TEMPLATE = (
    "⚡ Speed Test Results\n\n"
    "SPEEDTEST INFO:\n"
    "> Download: {download_mbps} Mbps ({download_bps}/s)\n"
    "> Upload: {upload_mbps} Mbps ({upload_bps}/s)\n"
    "> Ping: {ping} ms\n"
    "> Timestamp: {timestamp}\n"
    "> Data Sent: {bytes_sent}\n"
    "> Data Received: {bytes_received}\n\n"
    "SERVER INFO:\n"
    "> Name: {server_name}\n"
    "> Country: {server_country}\n"
    "> Sponsor: {server_sponsor}\n"
    "> Latency: {server_latency} ms\n"
    "> Coordinates: {server_lat}, {server_lon}\n\n"
    "CLIENT DETAILS:\n"
    "> IP: {client_ip}\n"
    "> Coordinates: {client_lat}, {client_lon}\n"
    "> ISP: {client_isp}\n"
    "> ISP Rating: {client_isprating}\n"
    "> Country: {client_country}"
)


def _run_speedtest():
    st = speedtest.Speedtest()
    st.get_best_server()
    st.download()
    st.upload(pre_allocate=False)

    # Sharing can be flaky; wrap safely
    share_url = None
    try:
        share_url = st.results.share()
    except Exception:
        share_url = None

    results = st.results.dict()
    if share_url:
        results["share"] = share_url
    return results


async def run_speedtest(retries: int = 2, delay: int = 3):
    loop = asyncio.get_running_loop()
    last_error = None
    for _ in range(retries + 1):
        try:
            return await loop.run_in_executor(None, _run_speedtest)
        except Exception as e:
            last_error = e
            await asyncio.sleep(delay)
            continue
    raise last_error


def format_speedtest(result: dict) -> str:
    download_bps = result.get("download", 0) / 8
    upload_bps = result.get("upload", 0) / 8

    server = result.get("server", {}) or {}
    client = result.get("client", {}) or {}

    return RESULT_TEMPLATE.format(
        download_mbps=round(result.get("download", 0) / 1_000_000, 2),
        download_bps=humanbytes(download_bps),
        upload_mbps=round(result.get("upload", 0) / 1_000_000, 2),
        upload_bps=humanbytes(upload_bps),
        ping=round(result.get("ping", 0), 2),
        timestamp=result.get("timestamp") or datetime.datetime.utcnow().isoformat(),
        bytes_sent=humanbytes(result.get("bytes_sent", 0)),
        bytes_received=humanbytes(result.get("bytes_received", 0)),
        server_name=server.get("name", "N/A"),
        server_country=server.get("country", "N/A"),
        server_sponsor=server.get("sponsor", "N/A"),
        server_latency=server.get("latency", "N/A"),
        server_lat=server.get("lat", "N/A"),
        server_lon=server.get("lon", "N/A"),
        client_ip=client.get("ip", "N/A"),
        client_lat=client.get("lat", "N/A"),
        client_lon=client.get("lon", "N/A"),
        client_isp=client.get("isp", "N/A"),
        client_isprating=client.get("isprating", "N/A"),
        client_country=client.get("country", "N/A"),
    )
