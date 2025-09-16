from django.core.management.base import BaseCommand
from django.db import connection, transaction

class Command(BaseCommand):
    help = "Удаляет импортированные данные (Workbook/Sheet/Cell/ImportBatch/Dataset/DatasetRow). По умолчанию — всё."

    def add_arguments(self, parser):
        parser.add_argument('--workbook-id', type=int, help='Удалить только по конкретному workbook_id')
        parser.add_argument('--like-filename', type=str, help="Удалить только те Workbooks, где filename ILIKE '%...%'")
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--fast', action='store_true', help='TRUNCATE ... RESTART IDENTITY CASCADE (только Postgres, всё сразу)')

    def handle(self, *args, **opts):
        wb_id = opts.get('workbook_id')
        like = opts.get('like_filename')
        dry  = opts.get('dry_run')
        fast = opts.get('fast')

        if fast and (wb_id or like):
            self.stderr.write(self.style.ERROR('--fast нельзя совмещать с фильтрами'))
            return

        with connection.cursor() as cur, transaction.atomic():
            if fast:
                if dry:
                    self.stdout.write('DRY-RUN: TRUNCATE ingest_datasetrow, ingest_dataset, ingest_cell, ingest_sheet, ingest_importbatch, ingest_workbook RESTART IDENTITY CASCADE;')
                    return
                cur.execute("""
                    TRUNCATE TABLE
                        ingest_datasetrow,
                        ingest_dataset,
                        ingest_cell,
                        ingest_sheet,
                        ingest_importbatch,
                        ingest_workbook
                    RESTART IDENTITY CASCADE;
                """)
                self.stdout.write(self.style.SUCCESS('TRUNCATE выполнен'))
                return

            # точечная очистка
            if wb_id or like:
                where = []
                params = []
                if wb_id:
                    where.append("id = %s")
                    params.append(wb_id)
                if like:
                    where.append("filename ILIKE %s")
                    params.append(f"%{like}%")
                sql = "SELECT id FROM ingest_workbook WHERE " + " AND ".join(where)
                cur.execute(sql, params)
                ids = [r[0] for r in cur.fetchall()]
                if not ids:
                    self.stdout.write('Нечего удалять.')
                    return
                self.stdout.write(f'Найдены Workbooks: {ids}')
                if dry:
                    self.stdout.write('DRY-RUN: будут удалены связанные Sheets/Cells/ImportBatches и Datasets/DatasetRows')
                    return
                cur.execute("DELETE FROM ingest_workbook WHERE id = ANY(%s);", (ids,))
                self.stdout.write(self.style.SUCCESS('Удалено каскадно по workbook фильтрам'))
            else:
                # удаление всего без TRUNCATE
                if dry:
                    self.stdout.write('DRY-RUN: DELETE FROM ingest_datasetrow/dataset/cell/sheet/importbatch/workbook')
                    return
                cur.execute("DELETE FROM ingest_datasetrow;")
                cur.execute("DELETE FROM ingest_dataset;")
                cur.execute("DELETE FROM ingest_cell;")
                cur.execute("DELETE FROM ingest_sheet;")
                cur.execute("DELETE FROM ingest_importbatch;")
                cur.execute("DELETE FROM ingest_workbook;")
                self.stdout.write(self.style.SUCCESS('Удалено всё импортированное (без TRUNCATE)'))
