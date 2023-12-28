"""
DeBasher package
Copyright 2019-2024 Daniel Ortiz-Mart\'inez

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
import getopt
import random
import string

##################################################
def take_pars():
    flags={}
    values={}
    flags["n_given"]=False
    flags["l_given"]=False
    flags["w_given"]=False

    try:
        opts, args = getopt.getopt(sys.argv[1:],"n:l:w:",["nlines=","linelen=","wordlen=","excl="])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
    if(len(opts)==0):
        print_help()
        sys.exit()
    else:
        for opt, arg in opts:
            if opt in ("-n", "--nlines"):
                values["nlines"] = int(arg)
                flags["n_given"]=True
            elif opt in ("-l", "--linelen"):
                values["linelen"] = int(arg)
                flags["l_given"]=True
            elif opt in ("-w", "--wordlen"):
                values["wordlen"] = int(arg)
                flags["w_given"]=True

    return (flags,values)

##################################################
def check_pars(flags,values):
    if(flags["n_given"]==False):
        print("Error! -n parameter not given", file=sys.stderr)
        sys.exit(2)
    if(flags["l_given"]==False):
        print("Error! -l parameter not given", file=sys.stderr)
        sys.exit(2)
    if(flags["w_given"]==False):
        print("Error! -w parameter not given", file=sys.stderr)
        sys.exit(2)

##################################################
def print_help():
    print("debasher_gen_telegram_data -n <int> -l <int> -w <int>", file=sys.stderr)
    print("", file=sys.stderr)
    print("-n <int>             Number of lines", file=sys.stderr)
    print("-l <int>             Maximum line length in words", file=sys.stderr)
    print("-w <int>             Maximum word length", file=sys.stderr)

##################################################
def generate_arbitrary_word(max_word_length=10):
    length = random.randint(1, max_word_length)
    return ''.join(random.choice(string.ascii_lowercase) for _ in range(length))

##################################################
def generate_arbitrary_words(max_line_length, max_word_length):
    line_length = random.randint(1, max_line_length)
    return ' '.join(generate_arbitrary_word(max_word_length) for _ in range(line_length))

##################################################
def print_arbitrary_words(n_lines, max_line_length, max_word_length):
    for _ in range(n_lines):
        line = generate_arbitrary_words(max_line_length, max_word_length)
        print(line)

##################################################
def process_pars(flags, values):
    print_arbitrary_words(n_lines=values['nlines'], max_line_length=values['linelen'], max_word_length=values['wordlen'])

##################################################
def main(argv):
    # take parameters
    (flags,values)=take_pars()

    # check parameters
    check_pars(flags,values)

    # process parameters
    process_pars(flags,values)

if __name__ == "__main__":
    main(sys.argv)
