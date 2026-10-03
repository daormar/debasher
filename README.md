<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)"
            srcset="rtdocs/source/images/debasher_logo_readme_dark.svg">
    <img src="rtdocs/source/images/debasher_logo_readme.svg"
         alt="DeBasher logo" width="400">
  </picture>
</p>

# DeBasher

DeBasher is a flow-based programming extension for Bash.

A DeBasher program is made of processes, written as Bash functions (or in
Python, R, Perl or Groovy), whose input and output options connect them;
those connections define the dependency graph that DeBasher schedules and
runs, in parallel where the data allows it. A general program processes a
batch of inputs and ends; a resident program is made of long-lived, stateful
processes that exchange messages through FIFOs and recover from crashes.
Programs can be written by hand or built, run and observed from a browser
with the DeBasher web interface.

Among its features:

- cycles between processes, and interactive workflows;
- stateful processes, with crash recovery, snapshots, and orderly stop and
  resume;
- a built-in scheduler, and Slurm for clusters;
- Conda environments and Docker containers for reproducibility;
- a web interface to build and run programs without writing their module.

## Installation

```bash
git clone https://github.com/daormar/debasher.git
cd debasher
./reconf
./configure --prefix=<installation-directory>
make
make install
```

DeBasher runs on Linux, and on Windows under WSL2; see the
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
