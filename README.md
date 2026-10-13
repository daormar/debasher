<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)"
            srcset="rtdocs/source/images/debasher_logo_readme_dark.svg">
    <img src="rtdocs/source/images/debasher_logo_readme.svg"
         alt="DeBasher logo" width="440">
  </picture>
</p>

# DeBasher

DeBasher is a workflow system whose processes are Unix programs. Each
process is written in the language its author prefers (Bash, Python, R,
Perl or Groovy), takes its inputs and gives its outputs through named
options, and the way options connect across processes defines the
dependency graph that DeBasher schedules and runs, on one machine or on a
Slurm cluster. Programs are built in a visual editor, with the help of an
AI assistant, or written by hand as Bash modules.

DeBasher runs two kinds of program. A general program processes a batch of
inputs and ends. A resident program processes a stream: long-lived,
stateful processes exchange messages through FIFOs, in cycles when needed,
survive crashes, and can launch a general program for each request they
receive. Both kinds define their processes the same way.

DeBasher follows flow-based programming and keeps what the shell does
best: a process is a black box with a command-line interface, so any
program that takes its inputs and leaves its outputs through options,
files or FIFOs can be one.

Among its features:

- cycles between processes, and interactive workflows;
- stateful processes, with crash recovery, snapshots, and orderly stop and
  resume;
- a built-in scheduler, and Slurm for clusters;
- Conda environments and Docker containers for reproducibility;
- a visual editor to build, run and observe programs from a browser, with
  AI assistance.

## Installation

```bash
git clone https://github.com/daormar/debasher.git
cd debasher
./reconf
./configure --prefix=<installation-directory>
make
make install
```

DeBasher runs on Linux, macOS and on Windows under WSL2; see the
[installation instructions](https://daormar.github.io/debasher/#installation)
for its requirements and for each system.

## Project information

- [Web page](https://daormar.github.io/debasher/)
- [Technical documentation](https://debasher.readthedocs.io/en/latest/)
- [Journal article](https://bmcbioinformatics.biomedcentral.com/articles/10.1186/s12859-025-06108-1)
- [Docker demo image](DOCKER.md)

## License and citation

DeBasher is released under the GNU Lesser General Public License, version 3.
If you use it in your research, please cite: Ortiz-Martínez, D. DeBasher: a
flow-based programming bash extension for the implementation of complex and
interactive workflows with stateful processes. BMC Bioinformatics 26, 106
(2025). https://doi.org/10.1186/s12859-025-06108-1
