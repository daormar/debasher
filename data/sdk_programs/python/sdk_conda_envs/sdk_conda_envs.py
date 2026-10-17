# The conda example of the web UI, described with the Python SDK: a
# process activates the Conda environment py27 and writes the version of
# its Python into a file. The environment is data (conda_envs=), from
# which the module writes the line that creates it, on a run with conda
# support, from py27.yml.

from debasher import Process, Program, in_outdir

python_version = Process("python_version", code="python_version.sh",
                         conda_envs={"py27": "py27.yml"},
                         description="Activates the conda environment py27 and writes the version "
                         "of its Python into a file.")
python_version.output("-outf", "file", "file with the version of the Python of py27",
                      in_outdir("python_version.txt"))

prg = Program(
    "sdk_conda_envs",
    description="Example described with the SDK: a general program whose process activates the "
    "conda environment py27, which a run with conda support creates from py27.yml, and writes "
    "the version of its Python into a file.",
    conda_support=True,
)
prg.add(python_version, cpus=1, mem=256, time="01:00:00")
