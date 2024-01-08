Getting Started
===============

Installing DeBasher and use it to implement a simple program is very
easy as it is show below.

.. _installation:

Installation
------------

Basic Installation Procedure
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To install DeBasher, first you need to install the autotools
(autoconf, autoconf-archive, automake and libtool packages in
Ubuntu). DeBasher requires Bash 4.0 or above as well as Python 3.x
to work. If you are planning to use DeBasher on a Windows
platform, you also need to install the
`Cygwin <https://www.cygwin.com/>`__ environment. Alternatively,
the tool can also be installed on Mac OS X systems using
`MacPorts <https://www.macports.org/>`__.

On the other hand, some of the functionality incorporated by
DeBasher requires the previous installation of third-party
software (`see below <#third-party-software>`__).

Once the autotools are available (as well as other required
software such as Cygwin or MacPorts), you can proceed with the
installation of the tool by following the next sequence of steps:

#. Obtain the package using git:

   ::

   $ git clone https://github.com/daormar/debasher.git

   Or `download it in a zip
   file <https://github.com/daormar/debasher/archive/master.zip>`__

#. ``cd`` to the directory containing the package's source code
   and type ``./reconf``.

#. Type ``./configure`` to configure the package.

#. Type ``make`` to compile the package.

#. Type ``make install`` to install the programs and any data
   files and documentation.

#. You can remove the program binaries and object files from the
   source code directory by typing ``make clean``.

By default the files are installed under the /usr/local/ directory
(or similar, depending on the OS you use); however, since Step 5
requires root privileges, another directory can be specified
during Step 3 by typing:

::

    $ configure --prefix=<absolute-installation-path>

For example, if "user1" wants to install the DeBasher package in
the directory /home/user1/debasher, the sequence of commands to
execute should be the following:

::

    $ ./reconf
    $ configure --prefix=/home/user1/debasher
    $ make
    $ make install

The installation directory can be the same directory where the
DeBasher package was decompressed.

.. _quickstart_example:

Quickstart Example
------------------

TBD
