from app.config import get_settings
from app.integrations.email_connector.service import _connect


def main() -> None:
    settings = get_settings()
    if not settings.email_configured:
        raise SystemExit("Email connector is disabled or incomplete.")
    connection = None
    try:
        connection = _connect()
        status, _data = connection.select(settings.email_imap_folder, readonly=True)
        if status != "OK":
            raise SystemExit("Email mailbox could not be selected read-only.")
        print("Email mailbox is reachable in read-only mode.")
    finally:
        if connection is not None:
            try:
                connection.logout()
            except Exception:
                pass


if __name__ == "__main__":
    main()
