import argparse

parser = argparse.ArgumentParser()
parser.add_argument("-s", default="Hello World!")
args = parser.parse_args()
print(args.s)
