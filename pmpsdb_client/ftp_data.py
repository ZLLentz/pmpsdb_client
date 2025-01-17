"""
Module to define the ftp file transfer interface.

This is how we upload database files to and download database files from the
PLCs. In order for this to work, the PLC needs to be configured to run its
FTP server.
"""
from __future__ import annotations

import datetime
import ftplib
import json
import logging
import os
import typing
from contextlib import contextmanager
from dataclasses import dataclass

DEFAULT_PW = (
    ('Administrator', '1'),
    ('webguest', '1'),
)
DIRECTORY = 'pmps'

logger = logging.getLogger(__name__)


@contextmanager
def ftp(hostname: str, directory: typing.Optional[str] = None) -> ftplib.FTP:
    """
    Context manager that manages an FTP connection.

    The connection will be opened and closed cleanly.
    This will be used as a helper in other functions.

    Parameters
    ----------
    hostname : str
        The plc hostname to connect to.
    directory : str, optional
        The ftp subdirectory to read to and write from.
        A default directory pmps is used if this argument is omitted.

    Yields
    ------
    ftp : ftplib.FTP
        An active FTP instance that can be used to read and write files.
    """
    logger.debug('ftp(%s, %s)', hostname, directory)
    # Default directory
    directory = directory or DIRECTORY
    # Create without connecting
    ftp_obj = ftplib.FTP(hostname, timeout=2.0)
    # Beckhoff docs recommend active mode
    ftp_obj.set_pasv(False)
    # Best-effort login using default passwords
    rval = None
    for user, pwd in DEFAULT_PW:
        try:
            logger.debug('Try user=%s', user)
            rval = ftp_obj.login(user=user, passwd=pwd)
        except ftplib.error_perm:
            pass
    # Fallback to anonymous login
    # Try last, might have reduced perms
    if rval is None:
        logger.debug('Try anonymous login')
        rval = ftp_obj.login()
    if rval is None:
        raise RuntimeError('Could not log into PLC using default passwords.')
    # Create directory if it does not exist
    if directory not in ftp_obj.nlst():
        ftp_obj.mkd(directory)
    # Put us into the proper directory
    ftp_obj.cwd(directory)
    # Should be ready to go
    yield ftp_obj
    # Cleanup
    try:
        # Polite cleanup
        ftp_obj.quit()
    except Exception:
        # Rude cleanup
        ftp_obj.close()


def list_filenames(
    hostname: str,
    directory: typing.Optional[str] = None,
) -> list[str]:
    """
    List the filenames that are currently saved on the PLC.

    Parameters
    ----------
    hostname : str
        The plc hostname to upload to.
    directory : str, optional
        The ftp subdirectory to read and write from
        A default directory pmps is used if this argument is omitted.

    Returns
    -------
    filenames : list of str
        The filenames on the PLC.
    """
    logger.debug('list_filenames(%s, %s)', hostname, directory)
    with ftp(hostname=hostname, directory=directory) as ftp_obj:
        return ftp_obj.nlst()


@dataclass
class PLCFile:
    """
    Information about a file on the PLC as learned through ftp.

    In the context of pmps, the create_time is the last time we
    updated the database export file.
    """
    filename: str
    create_time: datetime.datetime
    size: int

    @classmethod
    def from_list_line(cls, line: str) -> PLCFile:
        """
        Create a PLCFile from the output of the ftp LIST command.

        The output of this command is a series of lines representing
        information about the files in a directory.

        Here is a sample line of output:
        11-04-22  13:59                16439 kfe-motion.json

        Parameters
        ----------
        line : str
            A single line of text output from the ftp LIST command.
        """
        logger.debug('PLCFile.from_list_line(%s)', line)
        date, time, size, filename = line.split()
        month, day, year = date.split('-')
        hour, minute = time.split(':')
        full_datetime = datetime.datetime(
            year=int(year) + 2000,
            month=int(month),
            day=int(day),
            hour=int(hour),
            minute=int(minute),
        )
        return cls(
            filename=filename,
            create_time=full_datetime,
            size=int(size),
        )


def list_file_info(
    hostname: str,
    directory: typing.Optional[str] = None,
) -> list[PLCFile]:
    """
    Gather pertinent information about all the files.

    Parameters
    ----------
    hostname : str
        The plc hostname to connect to.
    directory : str, optional
        The ftp subdirectory to read and write from
        A default directory pmps is used if this argument is omitted.

    Returns
    -------
    info : list of PLCFile
        Information about our files, such as their creation times, sizes, and
        filenames.
    """
    logger.debug('list_file_info(%s, %s)', hostname, directory)
    lines = []
    with ftp(hostname=hostname, directory=directory) as ftp_obj:
        ftp_obj.retrlines('LIST', lines.append)
    return [PLCFile.from_list_line(line) for line in lines]


def upload_file(
    hostname: str,
    target_filename: str,
    fd: typing.BinaryIO,
    directory: typing.Optional[str] = None,
):
    """
    Upload an open file to a PLC.

    Parameters
    ----------
    hostname : str
        The plc hostname to upload to.
    target_filename : str
        The filename to save the file as on the target.
        This will overwrite an existing file with the same name.
    fd : file-like object
        A file-like object to upload.
    directory : str, optional
        The ftp subdirectory to read and write from
        A default directory pmps is used if this argument is omitted.
    """
    logger.debug(
        'upload_file(%s, %s, %s, %s)',
        hostname,
        target_filename,
        fd,
        directory,
    )
    with ftp(hostname=hostname, directory=directory) as ftp_obj:
        ftp_obj.storbinary(f'STOR {target_filename}', fd)


def upload_filename(
    hostname: str,
    filename: str,
    dest_filename: typing.Optional[str] = None,
    directory: typing.Optional[str] = None,
):
    """
    Open and upload a file on your filesystem to a PLC.

    Parameters
    ----------
    hostname : str
        The plc hostname to upload to.
    filename : str
        The name of the file on both your filesystem and on the PLC.
    directory : str, optional
        The ftp subdirectory to read and write from
        A default directory pmps is used if this argument is omitted.
    """
    logger.debug(
        'upload_file(%s, %s, %s, %s)',
        hostname,
        filename,
        dest_filename,
        directory,
    )
    with open(filename, 'rb') as fd:
        upload_file(
            hostname=hostname,
            target_filename=dest_filename or os.path.basename(filename),
            fd=fd,
            directory=directory,
        )


def download_file_text(
    hostname: str,
    filename: str,
    directory: typing.Optional[str] = None,
) -> str:
    """
    Download a file from the PLC to use in Python.

    The result is a single string, suitable for operations like
    json.loads

    Parameters
    ----------
    hostname : str
        The plc hostname to download from.
    filename : str
        The name of the file on the PLC.
    directory : str, optional
        The ftp subdirectory to read and write from
        A default directory pmps is used if this argument is omitted.

    Returns
    -------
    text: str
        The contents from the file.
    """
    logger.debug(
        'download_file_text(%s, %s, %s)',
        hostname,
        filename,
        directory,
    )
    byte_chunks = []
    with ftp(hostname=hostname, directory=directory) as ftp_obj:
        ftp_obj.retrbinary(f'RETR {filename}', byte_chunks.append)
    contents = ''
    for chunk in byte_chunks:
        contents += chunk.decode('ascii')
    return contents


def download_file_json_dict(
    hostname: str,
    filename: str,
    directory: typing.Optional[str] = None,
) -> dict[str, dict[str, typing.Any]]:
    """
    Download a file from the PLC and interpret it as a json dictionary.

    The result is suitable for comparing to json blobs exported from the
    pmps database.

    Parameters
    ----------
    hostname : str
        The plc hostname to download from.
    filename : str
        The name of the file on the PLC.
    directory : str, optional
        The ftp subdirectory to read and write from
        A default directory pmps is used if this argument is omitted.

    Returns
    -------
    data : dict
        The dictionary data from the file stored on the plc.
    """
    logger.debug(
        'download_file_json_dict(%s, %s, %s)',
        hostname,
        filename,
        directory,
    )
    return json.loads(
        download_file_text(
            hostname=hostname,
            filename=filename,
            directory=directory,
        )
    )


def local_file_json_dict(filename: str) -> dict[str, dict[str, typing.Any]]:
    """
    Return the json dict from a local file.

    Suitable for comparisons to files from the database or from the plc.

    Parameters
    ----------
    filename : str
        The name of the file on the local filesystem.

    Returns
    -------
    data : dict
        The dictionary data from the file stored on the local drive.
    """
    logger.debug('local_file_json_dict(%s)', filename)
    with open(filename, 'r') as fd:
        return json.load(fd)


def compare_file(
    hostname: str,
    local_filename: str,
    plc_filename: typing.Optional[str] = None,
    directory: typing.Optional[str] = None,
) -> bool:
    """
    Compare a file saved locally to one on the PLC.

    Parameters
    ----------
    hostname : str
        The plc hostname to download from.
    local_filename: str
        The full path the local file to compare with.
    plc_filename: str, optional
        The filename as saved on the PLC. If omitted, the local_filename's
        basename will be used.
    directory : str, optional
        The ftp subdirectory to read and write from
        A default directory pmps is used if this argument is omitted.

    Returns
    -------
    same_file : bool
        True if the contents of these two files are the same.
    """
    logger.debug(
        'compare_file(%s, %s, %s, %s)',
        hostname,
        local_filename,
        plc_filename,
        directory,
    )
    local_data = local_file_json_dict(filename=local_filename)
    plc_data = download_file_json_dict(
        hostname=hostname,
        filename=plc_filename,
        directory=directory,
    )
    return local_data == plc_data
