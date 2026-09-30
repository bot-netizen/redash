"""
Turning a pandas DataFrame into a query result.

Shared by the runners that read files -- CSV, Excel, Yandex Disk -- and by
the Python runner. pandas and numpy are 34 MB resident between them, and they
used to be imported the moment this module was, which meant every gunicorn
worker and every worker pod carried them whether or not the install had a
single file data source.

They are imported the first time one of these functions is called instead.
`from __future__ import annotations` is what makes that possible: without it
the `df: pd.DataFrame` annotations are evaluated when the functions are
defined, which would import pandas again at import time.
"""

from __future__ import annotations

import logging

from sqldesk.query_runner import (
    TYPE_BOOLEAN,
    TYPE_DATE,
    TYPE_DATETIME,
    TYPE_FLOAT,
    TYPE_INTEGER,
    TYPE_STRING,
    deferred,
    installed,
)

logger = logging.getLogger(__name__)

np = deferred("numpy")
pd = deferred("pandas")

#: Whether the SDKs are there, asked without importing them. The runners that
#: use this module read it to decide whether they are available at all.
pandas_installed = installed("pandas", "numpy")


def get_column_types_from_dataframe(df: pd.DataFrame) -> list:
    columns = []
    for column_name, dtype in df.dtypes.items():
        if dtype in (np.bool_,):
            column_type = TYPE_BOOLEAN
        elif dtype in (np.int64, np.int32):
            column_type = TYPE_INTEGER
        elif dtype in (np.float64,):
            column_type = TYPE_FLOAT
        elif dtype in (np.datetime64, np.dtype("<M8[ns]")):
            if df.empty:
                column_type = TYPE_DATETIME
            elif len(df[column_name].head(1).astype(str).loc[0]) > 10:
                column_type = TYPE_DATETIME
            else:
                column_type = TYPE_DATE
        else:
            column_type = TYPE_STRING

        columns.append({"name": column_name, "friendly_name": column_name, "type": column_type})

    return columns


def pandas_to_result(df: pd.DataFrame) -> dict:
    columns = get_column_types_from_dataframe(df)
    rows = df.to_dict("records")
    return {"columns": columns, "rows": rows}
