# *- python -*

# import modules
import io, sys, getopt

##################################################
class sample_data:
    def __init__(self):
        self.sample_alias=None
        self.filename=None
        self.fileaccession=None

##################################################
class analysis_data:
    def __init__(self):
        self.donor_id=None
        self.phenotype=None
        self.gender=None

##################################################
class study_data:
    def __init__(self):
        self.study_ega_id=None
        self.ega_sample_id=None

##################################################
def take_pars():
    flags={}
    values={}
    flags["s_given"]=False
    flags["a_given"]=False
    flags["t_given"]=False
    values["verbose"]=True

    try:
        opts, args = getopt.getopt(sys.argv[1:],"s:a:t:f:v",["sampleinfofile=","analysisinfofile=","studyinfofile=","format="])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
    if(len(opts)==0):
        print_help()
        sys.exit()
    else:
        for opt, arg in opts:
            if opt in ("-s", "--sampleinfofile"):
                values["sampleinfofile"] = arg
                flags["s_given"]=True
            if opt in ("-a", "--analysisinfofile"):
                values["analysisinfofile"] = arg
                flags["a_given"]=True
            if opt in ("-t", "--studyinfofile"):
                values["studyinfofile"] = arg
                flags["t_given"]=True
            if opt in ("-f", "--format"):
                values["format"] = int(arg)
                flags["f_given"]=True
            elif opt in ("-v", "--verbose"):
                verbose=1
    return (flags,values)

##################################################
def check_pars(flags,values):
    if(flags["s_given"]==False):
        print >> sys.stderr, "Error! -s parameter not given"
        sys.exit(2)

    if(flags["a_given"]==False):
        print >> sys.stderr, "Error! -a parameter not given"
        sys.exit(2)

    if(flags["t_given"]==False):
        print >> sys.stderr, "Error! -t parameter not given"
        sys.exit(2)

##################################################
def print_help():
    print >> sys.stderr, "query_ega_metadata -s <string> -a <string> -t <string> -f <int> [-v]"
    print >> sys.stderr, ""
    print >> sys.stderr, "-s <string>    File with sample information"
    print >> sys.stderr, "-a <string>    File with analysis information"
    print >> sys.stderr, "-t <string>    File with study information"
    print >> sys.stderr, "-f <int>       Output format:"
    print >> sys.stderr, "                1: SAMPLE_ACCESSION EGA_SAMPLE_ID FILE_ACCESSION FILENAME DONOR_ID PHENOTYPE GENDER"
    print >> sys.stderr, "-v             Verbose mode"

##################################################
def extract_sample_info(filename):
    sample_info_map={}
    file = open(filename, 'r')
    # read file line by line
    for line in file:
        line=line.strip("\n")
        fields=line.split()
        sample_accession=fields[1]
        sd=sample_data()
        sd.sample_alias=fields[0]
        sd.filename=fields[2]
        sd.fileaccession=fields[3]
        sample_info_map[sample_accession]=sd
    return sample_info_map

##################################################
def extract_attribute_info(line):
    fields=line.split()
    # Remove blanks from attributes
    attribute_str=""
    for i in range(1,len(fields)):
        attribute_str=attribute_str+"_"+fields[i]
    attr_fields=attribute_str.split(";")
    donor_id=attr_fields[1]
    phenotype=attr_fields[2]
    gender=attr_fields[4]

    return (donor_id,phenotype,gender)
        
##################################################
def extract_analysis_info(filename):
    analysis_info_map={}
    file = open(filename, 'r')
    # read file line by line
    for line in file:
        line=line.strip("\n")
        fields=line.split()
        ega_sample_id=fields[0]
        ad=analysis_data()
        (ad.donor_id,ad.phenotype,ad.gender)=extract_attribute_info(line)
        analysis_info_map[ega_sample_id]=ad
    return analysis_info_map

##################################################
def extract_study_info(filename):
    study_info_map={}
    file = open(filename, 'r')
    # read file line by line
    for line in file:
        line=line.strip("\n")
        fields=line.split()
        sample_accession=fields[len(fields)-3]
        sd=study_data()
        sd.study_ega_id=fields[0]
        sd.ega_sample_id=fields[len(fields)-1]
        study_info_map[sample_accession]=sd
    return study_info_map

##################################################
def print_info(format,sample_info_map,analysis_info_map,study_info_map):
    if(format==1):
        for sample_accession in study_info_map:
            ega_sample_id=study_info_map[sample_accession].ega_sample_id
            fileaccession=sample_info_map[sample_accession].fileaccession
            filename=sample_info_map[sample_accession].filename
            donor_id=analysis_info_map[ega_sample_id].donor_id
            phenotype=analysis_info_map[ega_sample_id].phenotype
            gender=analysis_info_map[ega_sample_id].gender
            print sample_accession,ega_sample_id,fileaccession,filename,donor_id,phenotype,gender
    
##################################################
def process_pars(flags,values):
    # Extract info from files
    sample_info_map=extract_sample_info(values["sampleinfofile"])
    analysis_info_map=extract_analysis_info(values["analysisinfofile"])
    study_info_map=extract_study_info(values["studyinfofile"])

    # Print information
    print_info(values["format"],sample_info_map,analysis_info_map,study_info_map)

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
