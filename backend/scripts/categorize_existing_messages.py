import argparse
import logging
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from app.db.session import SessionLocal
from app.services.categorization_service import CategorizationService


logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')


def main() -> None:
    parser = argparse.ArgumentParser(description='Categorize existing conversations from category keywords.')
    parser.add_argument('--batch-size', type=int, default=250)
    parser.add_argument('--all', action='store_true', help='Re-evaluate conversations that already have a category.')
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = CategorizationService(db).backfill_existing(
            batch_size=args.batch_size,
            only_uncategorized=not args.all,
        )
        logging.info(
            'Categorization complete processed=%s updated=%s unchanged=%s uncategorized=%s',
            result.processed,
            result.updated,
            result.unchanged,
            result.uncategorized,
        )
    finally:
        db.close()


if __name__ == '__main__':
    main()
