import argparse

# Create the parser
parser = argparse.ArgumentParser()

# Add the "-s" option with an integer argument
parser.add_argument('-s', type=str, required=True, help='String to be displayed')

# Parse the arguments
args = parser.parse_args()

# Access the value of "-s"
s = args.s

# Print message
print(s)
