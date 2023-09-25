"""
PanPipe package
Copyright 2019,2020 Daniel Ortiz-Mart\'inez

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public License
as published by the Free Software Foundation; either version 3
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program; If not, see <http://www.gnu.org/licenses/>.
"""

# *- python -*

# import modules
import io, sys, getopt, operator
from panpipe_ppl_lib import *

##################################################
def take_pars():
    flags={}
    values={}
    flags["p_given"]=False
    values["verbose"]=False

    try:
        opts, args = getopt.getopt(sys.argv[1:],"p:",["pfile="])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
    if(len(opts)==0):
        print_help()
        sys.exit()
    else:
        for opt, arg in opts:
            if opt in ("-p", "--pfile"):
                values["pfile"] = arg
                flags["p_given"]=True
            elif opt in ("-v", "--verbose"):
                flags["verbose"]=True
    return (flags,values)

##################################################
def check_pars(flags,values):
    if(flags["p_given"]==False):
        print("Error! -p parameter not given", file=sys.stderr)
        sys.exit(2)

##################################################
def print_help():
    print("pipe_check     -p <string> [-v]", file=sys.stderr)
    print("", file=sys.stderr)
    print("-p <string>    Pipeline file", file=sys.stderr)
    print("-v             Verbose mode", file=sys.stderr)

##################################################
def should_be_augmented(config_entries, process_entries):
    for entry in process_entries:
        if is_sub_ppl_entry(entry):
            return True
    return False

##################################################
def get_augmented_ppl(ppl_fname):
    # Extract info from ppl file
    config_entries = extract_config_entries(ppl_fname)
    entries_lineno, process_entries = extract_process_entries(ppl_fname)

    # Determine whether the file should be augmented or not
    if should_be_augmented(config_entries, process_entries):
        # Initialize variables
        augm_config_entries = config_entries
        augm_process_entries = []

        # Iterate over process entries
        for process_entry in process_entries:
            if is_sub_ppl_entry(process_entry):
                # The entry represents a sub-pipeline

                # Obtain sub-pipeline file name
                iter_ppl_fname = get_sub_ppl_fname(process_entry)

                # Extract corresponding config and process entries
                iter_cfg_entries, iter_process_entries = get_augmented_ppl(iter_ppl_fname)

                # Incorporate config entries
                augm_config_entries = iter_cfg_entries + augm_config_entries

                # Incorporate process entries
                for iter_process_entry in iter_process_entries:
                    augm_process_entries.append(iter_process_entry)
            else:
                # The entry does not represent a sub-pipeline
                augm_process_entries.append(process_entry)

        # Return augmented pipeline
        return augm_config_entries, augm_process_entries
    else:
        # No augmentation is needed
        return config_entries, process_entries

##################################################
def process_pars(flags,values):
    # Get augmented pipeline
    config_entries, process_entries = get_augmented_ppl(values["pfile"])

    # Print preprocessed ppl file
    print_entries(config_entries, process_entries)

##################################################
def main(argv):
    # take parameters
    (flags, values) = take_pars()

    # check parameters
    check_pars(flags, values)

    # process parameters
    success = process_pars(flags,values)

    exit(success)

if __name__ == "__main__":
    main(sys.argv)
