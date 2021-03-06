#!/usr/bin/env python
"""Utility for making a doctest file out of Python or IPython input.

  %prog [options] input_file [output_file]

This script is a convenient generator of doctest files that uses IPython's
irunner script to execute valid Python or IPython input in a separate process,
capture all of the output, and write it to an output file.

It can be used in one of two ways:

1. With a plain Python or IPython input file (denoted by extensions '.py' or
   '.ipy'.  In this case, the output is an auto-generated reST file with a
   basic header, and the captured Python input and output contained in an
   indented code block.

   If no output filename is given, the input name is used, with the extension
   replaced by '.txt'.

2. With an input template file.  Template files are simply plain text files
   with special directives of the form

   %run filename

   to include the named file at that point.

   If no output filename is given and the input filename is of the form
   'base.tpl.txt', the output will be automatically named 'base.txt'.
"""

# Standard library imports

import optparse
import os
import re
import sys
import tempfile

# IPython-specific libraries
from IPython.lib import irunner
from IPython.utils.warn import fatal

class IndentOut(object):
    """A simple output stream that indents all output by a fixed amount.

    Instances of this class trap output to a given stream and first reformat it
    to indent every input line."""

    def __init__(self,out=sys.stdout,indent=4):
        """Create an indented writer.

        :Keywords:

        - `out` : stream (sys.stdout)
          Output stream to actually write to after indenting.

        - `indent` : int
          Number of spaces to indent every input line by.
        """

        self.indent_text = ' '*indent
        self.indent = re.compile('^',re.MULTILINE).sub
        self.out = out
        self._write = out.write
        self.buffer = []
        self._closed = False

    def write(self,data):
        """Write a string to the output stream."""

        if self._closed:
            raise ValueError('I/O operation on closed file')
        self.buffer.append(data)

    def flush(self):
        if self.buffer:
            data = ''.join(self.buffer)
            self.buffer[:] = []
            self._write(self.indent(self.indent_text,data))

    def close(self):
        self.flush()
        self._closed = True

class RunnerFactory(object):
    """Code runner factory.

    This class provides an IPython code runner, but enforces that only one
    runner is every instantiated.  The runner is created based on the extension
    of the first file to run, and it raises an exception if a runner is later
    requested for a different extension type.

    This ensures that we don't generate example files for doctest with a mix of
    python and ipython syntax.
    """

    def __init__(self,out=sys.stdout):
        """Instantiate a code runner."""

        self.out = out
        self.runner = None
        self.runnerClass = None

    def _makeRunner(self,runnerClass):
        self.runnerClass = runnerClass
        self.runner = runnerClass(out=self.out)
        return self.runner

    def __call__(self,fname):
        """Return a runner for the given filename."""

        if fname.endswith('.py'):
            runnerClass = irunner.PythonRunner
        elif fname.endswith('.ipy'):
            runnerClass = irunner.IPythonRunner
        else:
            raise ValueError('Unknown file type for Runner: %r' % fname)

        if self.runner is None:
            return self._makeRunner(runnerClass)
        else:
            if runnerClass==self.runnerClass:
                return self.runner
            else:
                e='A runner of type %r can not run file %r' % \
                   (self.runnerClass,fname)
                raise ValueError(e)

TPL = """
=========================
 Auto-generated doctests
=========================

This file was auto-generated by IPython in its entirety.  If you need finer
control over the contents, simply make a manual template.  See the
mkdoctests.py script for details.

%%run %s
"""

def main():
    """Run as a script."""

    # Parse options and arguments.
    parser = optparse.OptionParser(usage=__doc__)
    newopt = parser.add_option
    newopt('-f','--force',action='store_true',dest='force',default=False,
           help='Force overwriting of the output file.')
    newopt('-s','--stdout',action='store_true',dest='stdout',default=False,
           help='Use stdout instead of a file for output.')

    opts,args = parser.parse_args()
    if len(args) < 1:
        parser.error("incorrect number of arguments")

    # Input filename
    fname = args[0]

    # We auto-generate the output file based on a trivial template to make it
    # really easy to create simple doctests.

    auto_gen_output = False
    try:
        outfname = args[1]
    except IndexError:
        outfname = None

    if fname.endswith('.tpl.txt') and outfname is None:
        outfname = fname.replace('.tpl.txt','.txt')
    else:
        bname, ext = os.path.splitext(fname)
        if ext in ['.py','.ipy']:
            auto_gen_output = True
        if outfname is None:
            outfname = bname+'.txt'

    # Open input file

    # In auto-gen mode, we actually change the name of the input file to be our
    # auto-generated template
    if auto_gen_output:
        infile = tempfile.TemporaryFile()
        infile.write(TPL % fname)
        infile.flush()
        infile.seek(0)
    else:
        infile = open(fname)

    # Now open the output file.  If opts.stdout was given, this overrides any
    # explicit choice of output filename and just directs all output to
    # stdout.
    if opts.stdout:
        outfile = sys.stdout
    else:
        # Argument processing finished, start main code
        if os.path.isfile(outfname) and not opts.force:
            fatal("Output file %r exists, use --force (-f) to overwrite."
                  % outfname)
        outfile = open(outfname,'w')


    # all output from included files will be indented
    indentOut = IndentOut(outfile,4)
    getRunner = RunnerFactory(indentOut)

    # Marker in reST for transition lines
    rst_transition = '\n'+'-'*76+'\n\n'

    # local shorthand for loop
    write = outfile.write

    # Process input, simply writing back out all normal lines and executing the
    # files in lines marked as '%run filename'.
    for line in infile:
        if line.startswith('%run '):
            # We don't support files with spaces in their names.
            incfname = line.split()[1]

            # We make the output of the included file appear bracketed between
            # clear reST transition marks, and indent it so that if anyone
            # makes an HTML or PDF out of the file, all doctest input and
            # output appears in proper literal blocks.
            write(rst_transition)
            write('Begin included file %s::\n\n' % incfname)

            # I deliberately do NOT trap any exceptions here, so that if
            # there's any problem, the user running this at the command line
            # finds out immediately by the code blowing up, rather than ending
            # up silently with an incomplete or incorrect file.
            getRunner(incfname).run_file(incfname)

            write('\nEnd included file %s\n' % incfname)
            write(rst_transition)
        else:
            # The rest of the input file is just written out
            write(line)
    infile.close()

    # Don't close sys.stdout!!!
    if outfile is not sys.stdout:
        outfile.close()

if __name__ == '__main__':
    main()
