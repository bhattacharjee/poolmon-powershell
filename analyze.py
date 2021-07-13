#!/usr/bin/env python3

# Author: Rajbir Bhattacharjee

"""
This script helps analyze memory leaks. It plots a graph for each tag.
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import argparse
import glob
import dateutil
import codecs
from matplotlib.ticker import FormatStrFormatter
import seaborn as sns

class PoolEntries:
    def __init__(self):
        self.individual_data_frames = list()
        self.pool_entries = None
        self.digest_called = False

    # ------------------------------------------------------------------------

    def GetEncoding(self, filename:str) -> str:
        """
        Try to guess the encoding of a file

        Parameters
        ----------
        filename : str
            The filename for which the encoding is to be guessed.

        Returns
        -------
        str
            The encoding. If it fails to find an encoding, it returns utf-8.

        """
        with open(filename, mode="rb") as f:
            fbytes = f.read(64)
            BOMS = (
                (codecs.BOM_UTF8, "utf-8"),
                (codecs.BOM_UTF16, "utf-16"),
                (codecs.BOM_UTF32_BE, "utf-32be"),
                (codecs.BOM_UTF32_LE, "utf-32le"),
                (codecs.BOM_UTF16_BE, "utf-16be"),
                (codecs.BOM_UTF16_LE, "utf-16le"),
            )
            try:
                return [encoding for bom, encoding in BOMS \
                        if fbytes.startswith(bom)][0]
            except:
                return "utf-8"

    # ------------------------------------------------------------------------

    def add_csv_file(self, csv_file:str) -> None:
        """
        Read a CSV file and add all its entries to the pool

        Parameters
        ----------
        csv_file : str
            The CSV file to add to the list.

        Returns
        -------
        None
            No return.

        """
        df = pd.read_csv(\
            csv_file,\
            encoding=self.GetEncoding(csv_file),\
            parse_dates=True,\
            date_parser=dateutil.parser.parser)
        df['DateTime'] = pd.to_datetime(\
            df['DateTime'],\
            format=('%Y-%m-%dT%H:%M:%S'))
        df['DateTimeUTC'] = pd.to_datetime(\
            df['DateTimeUTC'],\
            format=('%Y-%m-%dT%H:%M:%S'))
        self.individual_data_frames.append(df)

    # ------------------------------------------------------------------------

    def add_totals_row(\
            self, \
            df:pd.DataFrame) -> pd.DataFrame:
        """
        Individual CSV files have all the tags at that moment, and each
        entry forms a tag. But there is no tag for all the tags combined.
        This function adds an entry for the total at any instance.

        Parameters
        ----------
        df : pd.DataFrame
            Input dataframe, this is one full CSV file equivalent at an
            instance
        templateDf : TYPE
            The template of the dataframe

        Returns
        -------
        pd.DataFrame
            The Dataframe with a total's row added

        """  
        column_types = {i:str(df.dtypes[i]) for i in df.columns}
        total_row_series = df.loc[0].copy()
        total_row_series["Tag"] = "TOTAL"
        for colname, coltype in column_types.items():
            if coltype.startswith('int'):
                total_row_series[colname] = df[colname].sum()
        df = df.append(total_row_series, ignore_index=True)
        return df

    # ------------------------------------------------------------------------

    def digest(self) -> pd.DataFrame:
        """
        Call this after adding all CSV files

        Returns
        -------
        pd.DataFrame
            Returns the DataFrame

        """

        if self.digest_called:
            raise Exception("digest() called again")
        self.digest_called = True

        all_dfs = []
        for df in self.individual_data_frames:
            df = self.add_totals_row(df)
            all_dfs.append(df)
        self.pool_entries = pd.concat(all_dfs)
        del(self.individual_data_frames)
        self.individual_data_frames = None

        # Sort by timestamp
        # First find the timestamp column name
        col_types = {i:str(self.pool_entries.dtypes[i]) for i in df.columns}
        date_col_name = None
        for colname, coltype in col_types.items():
            if coltype.startswith('datetime'): date_col_name = colname
        # Then sort by that column
        self.pool_entries.sort_values(\
            date_col_name,\
            ascending=True,\
            inplace=True,\
            ignore_index=True)

        self.pool_entries['TotalDiff'] = \
            self.pool_entries['PagedDiff'] + self.pool_entries['NonPagedDiff']
        return self.pool_entries

    # ------------------------------------------------------------------------

    def get_df(self) -> pd.DataFrame:
        """
        Get the dataframe

        Returns
        -------
        pd.DataFrame
            Returns the dataframe that is an aggregate of all time steps
            and includes TOTAL counts as well

        """
        if not self.digest_called: self.digest()
        return self.pool_entries

    # ------------------------------------------------------------------------

    def get_all_tags(self) -> list:
        """
        returns all tags that we've seen so far

        Returns
        -------
        List(str)
            All tags.

        """
        if not self.digest_called: self.digest()
        return [t for t in self.pool_entries['Tag'].unique()]

    # ------------------------------------------------------------------------

    def get_highest_tags(\
            self,\
            n_tags:int,\
            by_col:str="TotalUsedBytes",\
            ignore_tags:list=[]) -> list:
        """
        Get the list of tags that have the highest usage        

        Parameters
        ----------
        n_tags : int
            Number of highest tags to get.
        by_col : str, optional
            Which column to calculate the highest usage by.
            The default is "TotalUsedBytes".
        ignore_tags : list, optional
            These columns will not be considered for efficiency.
            The default is [].
        Returns
        -------
        List(str)
            List of tags that have the highest usage.
        """
        if ignore_tags is None or not isinstance(ignore_tags, list):
            ignore_tags = []
        ignore_tags.append('TOTAL')
        reduced_df = \
            self.pool_entries[~self.pool_entries['Tag'].isin(ignore_tags)]
        reduced_df = reduced_df[['Tag', by_col]]
        top_users = reduced_df.groupby(['Tag'])\
                                .max()\
                                .sort_values([by_col], ascending=False)\
                                .head(n_tags)
        return [row.name for _ , row in top_users.iterrows()]

    # ------------------------------------------------------------------------

    def get_most_changed_tags(\
            self,\
            n_tags:int,\
            by_col:str="TotalUsedBytes",\
            ignore_tags:list=[]) -> list:
        """
        Get the list of tags that see the highest change
        Highest change here is the difference between the first and the
        last entry

        Parameters
        ----------
        n_tags : int
            Number of highest tags to get.
        by_col : str, optional
            Which column to calculate the highest usage by.
            The default is "TotalUsedBytes".
        ignore_tags : list, optional
            These columns will not be considered for efficiency.
            The default is [].
        Returns
        -------
        List(str)
            List of tags that have the highest usage.
        """

        def get_change(x):
            (first, last) = tuple(x.to_numpy()[[0,-1]])
            return last - first

        if ignore_tags is None or not isinstance(ignore_tags, list):
            ignore_tags = []
        ignore_tags.append('TOTAL')
        reduced_df = \
            self.pool_entries[~self.pool_entries['Tag'].isin(ignore_tags)]
        reduced_df = reduced_df[['Tag', by_col]]

        g = reduced_df[['Tag', by_col]]\
                .groupby(['Tag'])\
                .agg(get_change)\
                .sort_values([by_col], ascending=False)\
                .head(n_tags)

        return [row.name for _ , row in g.iterrows()]

    # ------------------------------------------------------------------------

    def show_plot(\
            self,\
            tags: list,\
            timestamp_tag:str='DateTimeUTC',
            by_col:str='TotalUsedBytes',
            rcparams:dict=None) -> None:
        """
        Plot a set of tags and display

        Parameters
        ----------
        tags : list
            List of tags to plot
        timestamp_tag : str, optional
            Timestamp, localtime or UTC. The default is 'DateTimeUTC'.
            The other valid value is DateTime
        by_col : str, optional
            Which column to look at. The default is 'TotalUsedBytes'.
            Other possible values are:
                PagedDiff
                NonPagedDiff,
                TotalDiff,
                PagedUsedBytes,
                NonPagedUsedBytes,
                TotalUsedBytes
        rcparams : dict, optional
            rcParams for matplotlib. The default is None.

        Returns
        -------
        None
            DESCRIPTION.

        """
        if timestamp_tag not in ['DateTime', 'DateTimeUTC']:
            raise Exception('Invalid timestamp tag')

        valid_cols = ['TotalUsedBytes', 'PagedDiff', 'NonPagedDiff',\
                      'TotalDiff', 'PagedUsedBytes', 'NonPagedUsedBytes']
        if by_col not in valid_cols:
            raise Exception('Invalid column name')

        if None is not rcparams: plt.rcParams.update(rcparams)

        title = by_col
        reduced_df = self.pool_entries[self.pool_entries['Tag'].isin(tags)]
        reduced_df = reduced_df[['Tag', by_col, 'DateTimeUTC']]
        xformatter = FormatStrFormatter('%d')

        if by_col.endswith('Bytes'):
            reduced_df = reduced_df.copy()
            reduced_df[[by_col]] = reduced_df[[by_col]].divide(1024 * 1024)
            title = f"{by_col} (MB)"
            xformatter = FormatStrFormatter('%.3f')
        else:
            title = f"{by_col} (n_allocs)"

        print("just about to plot")
        ax = reduced_df.pivot(\
                        index='DateTimeUTC',\
                        values=by_col,\
                        columns='Tag').plot(marker='.')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S'))
        ax.yaxis.set_major_formatter(xformatter)
        ax.set_title(title)

        colorScheme = 'seaborn'
        plt.style.use([colorScheme])
        plt.style.context(colorScheme)

        plt.show()

    # -----------------------------------------------------------------------
    def do_plot(\
            self,\
            by_col:str='TotalUsedBytes',\
            timestamp_tag:str='DateTimeUTC',\
            ignore_tags:list=None,\
            include_tags:list=None,\
            rcparams:dict=None,\
            n_most_changed:int=5,\
            n_highest:int=5) -> None:
        """
        Plot a column

        Parameters
        ----------
        by_col : str, optional
            The column to plot. The default is 'TotalUsedBytes'.
            Other possible values are:
                PagedDiff
                NonPagedDiff,
                TotalDiff,
                PagedUsedBytes,
                NonPagedUsedBytes,
                TotalUsedBytes
        timestamp_tag : str, optional
            Whether to use localtime or UTC. The default is 'DateTimeUTC'.
        ignore_tags : list, optional
            List of tags to ignore. The default is None.
        include_tags : list, optional
            List of tags to include. The default is None.
        rcparams : dict, optional
            rcParams for matplotlib configuration. The default is None.
        n_most_changed : int, optional
            Number of tags that show highest increase. The default is 5.
        n_highest : int, optional
            Number of tags that have highest peak usage. The default is 5.

        Raises
        ------
        Exception
            DESCRIPTION.

        Returns
        -------
        None
            DESCRIPTION.

        """

        if timestamp_tag not in ['DateTime', 'DateTimeUTC']:
            raise Exception('Invalid timestamp tag')

        valid_cols = ['TotalUsedBytes', 'PagedDiff', 'NonPagedDiff',\
                      'TotalDiff', 'PagedUsedBytes', 'NonPagedUsedBytes']
        if by_col not in valid_cols:
            raise Exception('Invalid column name')

        if None is include_tags or not isinstance(include_tags, list):
            include_tags = []

        if not self.digest_called: self.digest()

        most_changed_tags = []
        if n_most_changed > 0:
            most_changed_tags = self.get_most_changed_tags(\
                                            n_tags=n_most_changed,\
                                            by_col=by_col,\
                                            ignore_tags=ignore_tags)
        highest_tags = []
        if n_highest > 0:
            highest_tags = self.get_highest_tags(\
                                            n_tags=n_highest,\
                                            by_col=by_col,\
                                            ignore_tags=ignore_tags)

        all_tags = ['TOTAL']
        for t in include_tags:
            if t not in all_tags:
                all_tags.append(t)
        for t in most_changed_tags:
            if t not in all_tags:
                all_tags.append(t)
        for t in highest_tags:
            if t not in all_tags:
                all_tags.append(t)

        self.show_plot(\
                tags=all_tags,\
                timestamp_tag=timestamp_tag,\
                by_col=by_col, rcparams=rcparams)

    # -----------------------------------------------------------------------

# ---------------------------------------------------------------------------


def read_directory(dirname:str) -> PoolEntries:
    """
    Reads a directory and returns all the items in a PoolEntry structure

    Parameters
    ----------
    dirname : str
        Name of the directory.

    Returns
    -------
    PoolEntries
        The entries from all the CSV files in the directory.

    """
    pe = PoolEntries()
    for fname in glob.glob(f"{dirname}/*pool.csv"):
        pe.add_csv_file(fname)
    pe.do_plot(by_col='TotalDiff')

def main():
    """
    parser = argparse.ArgumentParser("Analyze Poolmon")
    parser.add_argument(\
                        "-d",\
                        "--directory",\
                        help="The directory where the CSV files reside",\
                        required=True)
    args = parser.parse_args()
    """
    read_directory(".")


if "__main__" == __name__:
    main()