"""Kodoja pipeline."""
from __future__ import print_function

import subprocess
import pandas as pd
import random
import os
import pickle
from math import isnan

from Bio import SeqIO
from Bio.SeqIO.FastaIO import SimpleFastaParser
from Bio.SeqIO.QualityIO import FastqGeneralIterator

# The user-facing scripts will all report this version number via --version:
version = "0.0.9"


def check_path(dirs):
    """Check if directory path has '/' at the end.

    Return value is either '/' or empty string ''.
    """
    if dirs[-1] != "/":
        return "/"
    else:
        return ""


def test_format(file1, user_format):
    """Check data format.

    Check if data is in the fasta or fastq format and
    assert the user has specified the correct format for
    the data provided.

    Return an assert stament and stop or continue.
    """
    with open(file1) as myfile:
        # Would have used xrange under Python 2, but want this to work
        # on both Python 2 and 3 and a list of 8 elements is tiny.
        small_file = [next(myfile) for x in range(8)]

    file_format = "not identified"

    if small_file[0][0] == "@" and small_file[4][0] == "@":
        file_format = "fastq"
    if small_file[0][0] == ">":
        file_format = "fasta"

    assert (file_format == "fasta") | (file_format == "fastq"), \
        "Cannot proceed with file as it is not in fasta or fastq format."
    assert user_format == file_format, \
        "File has been detected to be in " + file_format + \
        " format rather than " + user_format + " format."


def rename_seqIDs(input_file, out_dir, user_format, paired=False):
    """Rename sequence identifiers to just the read number.

    Write a new file where each sequence ID is replaced with
    the read number (counting from one).

    Does not attempt to include "/1" and "/2" name suffixes, nor
    include "1:" or "2:" in the description, for paired reads.

    Returns dictionary mapping the sequence number to the old
    identifier (first word only from the description line,
    and if paired without any "/1" or "/2" suffix).

    See also read_names_by_number for recovering the dictionary.
    """
    if paired == 2:
        output_file = os.path.join(out_dir, "renamed_file_2." + user_format)
    elif paired == 1 or paired is False:
        output_file = os.path.join(out_dir, "renamed_file_1." + user_format)
    else:
        raise ValueError("Wanted 1, 2 or False - not %r" % paired)
    id_dict = {}
    with open(input_file, 'r') as in_file, open(output_file, 'w') as out_file:
        if user_format == 'fasta':
            for index, (title, seq) in enumerate(SimpleFastaParser(in_file)):
                name = title.split(None, 1)[0]
                if (paired == 1 and name.endswith("/1")) or (paired == 2 and name.endswith("/2")):
                    name = name[:-2]
                id_dict[index + 1] = name
                out_file.write(">%i\n%s\n" % (index + 1, seq))
        else:
            for index, (title, seq, qual) in enumerate(FastqGeneralIterator(in_file)):
                name = title.split(None, 1)[0]
                if (paired == 1 and name.endswith("/1")) or (paired == 2 and name.endswith("/2")):
                    name = name[:-2]
                id_dict[index + 1] = name
                out_file.write("@%i\n%s\n+\n%s\n" % (index + 1, seq, qual))
    return id_dict


def read_names_by_number(input_file, user_format):
    """For mapping read numbers back to original read titles.

    Essentially to undo the mapping from rename_seqIDs when we
    come to analyse the Kraken or Kaiju ouput.
    """
    id_dict = {}
    with open(input_file, 'r') as in_file:
        if user_format == 'fasta':
            for index, (title, seq) in enumerate(SimpleFastaParser(in_file)):
                id_dict[index + 1] = title
        else:
            for index, (title, seq, qual) in enumerate(FastqGeneralIterator(in_file)):
                id_dict[index + 1] = title
    return id_dict


def check_file(file1, out_dir, user_format, file2=False):
    """Rename sequnce ids and check PE files.

    Rename sequnce ids for SE or PE files to ensure
    consistency between kraken and kaiju (which modify
    id names). Create dictionaries containing real IDs and
    renamed version. If data is PE, assert
    paired files have the same number of entries and if
    the paired reads are matched by choosing random
    entries and confirming the IDs match (optionally
    with /1 and /2 suffixes).
    """
    if file2:
        ids1 = rename_seqIDs(file1, out_dir, user_format, paired=1)
        ids2 = rename_seqIDs(file2, out_dir, user_format, paired=2)

        assert len(ids1) == len(ids2), \
            "Paired files have different number of reads"

        for values in range(1, 50):
            random_id = random.randint(1, len(ids1) - 1)
            id_1 = ids1[random_id]
            id_2 = ids2[random_id]
            assert id_1 == id_2, \
                ("Paired-end sequences don't match, e.g. %r vs %r"
                 % (id_1, id_2))
    else:
        ids1 = rename_seqIDs(file1, out_dir, user_format, paired=False)

    with open(os.path.join(out_dir, "log_file.txt"), "a") as log_file:
        log_file.write("Number of sequences = " + str(list(ids1)[-1]) + "\n")


def fastqc_trim(out_dir, file1, trim_minlen, threads, adapter_file, file2=False):
    """Quality and adaptor trimming of fastq files.

    Takes fastq data (either single or paired), trims sequences using trimmomatic
    (in the case of paried end reads, it deletes extra files) and uses fastqc to
    show the user what the sequence quality looks like after trimming.

    Returns trimmed sequence files and fastq analysis files
    """
    trimAdapt_command = " LEADING:20 TRAILING:20 MINLEN:" + \
                        str(trim_minlen)
    if adapter_file:
        trimAdapt_command += " ILLUMINACLIP:" + adapter_file + ":2:30:10"

    if file2:
        PE_trim_command = "trimmomatic PE -threads " + str(threads) + " " + file1 + " " + file2 + \
            " " + os.path.join(out_dir, "trimmed_read1") + \
            " " + os.path.join(out_dir, "PE_trimmed_data_1U") + \
            " " + os.path.join(out_dir, "trimmed_read2") + \
            " " + os.path.join(out_dir, "PE_trimmed_data_2U") + trimAdapt_command

        subprocess.check_call(PE_trim_command, shell=True)
        os.remove(os.path.join(out_dir, "PE_trimmed_data_1U"))
        os.remove(os.path.join(out_dir, "PE_trimmed_data_2U"))
        subprocess.check_call("fastqc " + os.path.join(out_dir, "trimmed_read1") +
                              " -o " + out_dir, shell=True)
        subprocess.check_call("fastqc " + os.path.join(out_dir, "trimmed_read2") +
                              " -o " + out_dir, shell=True)
    else:
        subprocess.check_call("trimmomatic SE -threads " + str(threads) + " " + file1 +
                              " " + os.path.join(out_dir, "trimmed_read1") +
                              " " + trimAdapt_command, shell=True)
        subprocess.check_call("fastqc " + os.path.join(out_dir, "trimmed_read1") +
                              " -o " + out_dir, shell=True)


def kraken_classify(out_dir, kraken_file1, threads, user_format, kraken_db, kraken_file2=False,
                    quick_minhits=False, preload=False):
    """Kraken classification.

    Add appropiate switches for kraken command (format, preload, minimum hits,
    if paired or single end) and call
    kraken command, followed by kraken-translate to get full taxonomy for each
    sequence based on thir sequence id (Seq_tax: d__superkingdom, k__kingdom,
    p__phylum, c__class, o__order, f__family, g__genus, s__species).

    Return kraken_table file with a row for each sequence and kraken classification
    (or unclassified) and kraken_labels file witha row for each sequence that was
    classified by kraken with full taxonomy.
    """
    if user_format == "fastq":
        format_switch = " --fastq-input"
    elif user_format == "fasta":
        format_switch = " --fasta-input"

    if preload:
        kraken_command = "kraken --preload "
    else:
        kraken_command = "kraken "

    kraken_command += "--threads " + str(threads) + " --db " + kraken_db + format_switch

    if quick_minhits:
        kraken_command += " --quick --min-hits " + str(quick_minhits)

    if kraken_file2:
        kraken_command += " --paired " + kraken_file1 + " " + \
                          kraken_file2 + " > " + os.path.join(out_dir, "kraken_table.txt")
    else:
        kraken_command += " " + kraken_file1 + " > " + os.path.join(out_dir, "kraken_table.txt")

    subprocess.check_call(kraken_command, shell=True)
    subprocess.check_call("kraken-translate --mpa-format --db " + kraken_db +
                          " " + os.path.join(out_dir, "kraken_table.txt") + " > " +
                          os.path.join(out_dir, "kraken_labels.txt"), shell=True)


def format_result_table(out_dir, data_table, data_labels, table_colNames):
    """Merge classification and label data.

    Merge the classification data (either kraken or kaiju) with the 'label'
    data which has full taxonomy for the classified sequence.

    Return merged table
    """
    label_colNames = ["Seq_ID", "Seq_tax"]
    seq_data = pd.read_csv(os.path.join(out_dir, data_table),
                           sep="\t", header=None, names=table_colNames,
                           index_col=False)
    seq_labelData = pd.read_csv(os.path.join(out_dir, data_labels),
                                sep="\t", header=None,
                                names=label_colNames)
    seq_result = pd.merge(seq_data, seq_labelData, on='Seq_ID', how='outer')
    return seq_result


def filter_sequence_file(input_file, output_file, user_format, wanted,
                         ignore_suffix=None):
    """Create a subset of sequences based on sequence IDs.

    Writes a FASTA or FASTQ file in the output file specified.

    Argument wanted should be a Python set of identifers (with no white space,
    i.e. the first word only from the FASTA or FASTQ title lines).

    Optional argument ignore_suffix="/1" means remove any suffix "/1"
    from the input read names before matching to the wanted list.
    The suffix is retained in the output file.
    """
    print("Selecting %i unique identifiers" % len(wanted))
    if ignore_suffix:
        cut = len(ignore_suffix)
        records = (r for r in SeqIO.parse(input_file, user_format)
                   if (r.id[:-cut] if r.id.endswith(ignore_suffix) else r.id) in wanted)
    else:
        records = (r for r in SeqIO.parse(input_file, user_format)
                   if r.id in wanted)
    count = SeqIO.write(records, output_file, user_format)
    print("Saved %i records from %s to %s" % (count, input_file, output_file))
    if count < len(wanted):
        print("Warning %i IDs not found in %s" % (len(wanted) - count, input_file))


def seq_reanalysis(kraken_table, kraken_labels, out_dir, user_format, reads_file1):
    """Format table and subset sequences for kaiju analysis.

    Merge kraken_table and kraken_labels using format_result_table() and write to disk
    (delete kraken_table and kraken_label).

    Return merged kraken tableresult tables and subsetted sequence files (i subset=True).

    It needs an original FASTA/FASTQ file in order to recover the read names
    since we run Kraken (and Kaiju) with reads renamed to just their read number.
    """
    kraken_colNames = ["kraken_classified", "Seq_ID", "Tax_ID", "kraken_length",
                       "kraken_k-mer"]
    kraken_fullTable = format_result_table(out_dir, "kraken_table.txt",
                                           "kraken_labels.txt", kraken_colNames)
    kraken_fullTable['Seq_ID'] = kraken_fullTable['Seq_ID'].astype(float)
    kraken_fullTable['Seq_ID'] = kraken_fullTable['Seq_ID'].astype(int)

    kraken_results = kraken_fullTable[["kraken_classified", "Seq_ID", "Tax_ID", "Seq_tax"]]
    kraken_results.to_csv(os.path.join(out_dir, 'kraken_VRL.txt'),
                          sep='\t', index=False)

    ids1 = read_names_by_number(reads_file1, user_format)
    kraken_fullTable["Seq_ID"] = kraken_fullTable["Seq_ID"].map(ids1)
    kraken_fullTable.to_csv(os.path.join(out_dir, "kraken_FormattedTable.txt"),
                            sep='\t', index=False)
    if os.path.isfile(os.path.join(out_dir, "kraken_FormattedTable.txt.gz")):
        os.remove(os.path.join(out_dir, "kraken_FormattedTable.txt.gz"))
    subprocess.check_call("gzip " + os.path.join(out_dir, "kraken_FormattedTable.txt"),
                          shell=True)
    os.remove(os.path.join(out_dir, "kraken_table.txt"))
    os.remove(os.path.join(out_dir, "kraken_labels.txt"))


def kaiju_classify(kaiju_file1, threads, out_dir, kaiju_db, kaiju_minlen, kraken_db,
                   kaiju_file2=False, kaiju_mismatch=False, kaiju_score=False):
    """Run kaiju command for kaiju classification of sequences.

    It ensures that if mismatches are allowed that a score has also been provided.
    Once classification is complete, it uses kraken-translate (as in kraken_classify())
    to get full taxonomy names for each sequence that has been classified. It deletes the files
    used for this analysis.

    """
    kaiju_nodes = kraken_db + "taxonomy/nodes.dmp"
    kaiju_fmi = kaiju_db + "kaiju_library.fmi"
    # kaiju_names = kaiju_db + "names.dmp"

    if kaiju_mismatch:
        assert(kaiju_score), "Set kaiju_score for greedy mode"
        mode = "greedy -e " + str(kaiju_mismatch) + " -s " + str(kaiju_score)
    else:
        mode = "mem"

    kaiju_command = "kaiju -z " + str(threads) + " -t " + kaiju_nodes + " -f " + kaiju_fmi + \
                    " -i " + kaiju_file1 + " -o " + os.path.join(out_dir, "kaiju_table.txt") + \
                    " -x -v -a " + mode + " -m " + str(kaiju_minlen)

    if kaiju_file2:
        kaiju_command += " -j " + kaiju_file2

    subprocess.check_call(kaiju_command, shell=True)
    subprocess.check_call("kraken-translate --mpa-format --db " + kraken_db + " " +
                          os.path.join(out_dir, "kaiju_table.txt") + " > " +
                          os.path.join(out_dir, "kaiju_labels.txt"), shell=True)

    for dirs, sub_dirs, files in os.walk(out_dir):
        # Only delete file when it's in out_put
        for filenames in files:
            if kaiju_file1 == filenames:
                os.remove(kaiju_file1)
                if kaiju_file2:
                    os.remove(kaiju_file2)


def result_analysis(out_dir, kraken_VRL, kaiju_table, kaiju_label, host_subset,
                    user_format, reads_file1):
    """Kodoja results table.

    Imports kraken results table, formats kaiju_table and kaiju_labels and merges
    kraken and kaiju results into one table (kodoja). It then makes a table with
    all identified species and count number of intances for each usin virusSummary().

    It needs an original FASTA/FASTQ file in order to recover the read names
    since we run Kraken (and Kaiju) with reads renamed to just their read number.
    """
    kraken_results = pd.read_csv(os.path.join(out_dir + kraken_VRL),
                                 header=0, sep='\t',
                                 dtype={"kraken_classified": str, "Seq_ID": int,
                                        "Tax_ID": int, "Seq_tax": str})

    kaiju_colNames = ["kaiju_classified", "Seq_ID", "Tax_ID", "kaiju_lenBest",
                      "kaiju_tax_AN", "kaiju_accession", "kaiju_fragment"]
    kaiju_fullTable = format_result_table(out_dir, "kaiju_table.txt", "kaiju_labels.txt",
                                          kaiju_colNames)
    kaiju_fullTable['Seq_ID'] = kaiju_fullTable['Seq_ID'].astype(float)
    kaiju_fullTable['Seq_ID'] = kaiju_fullTable['Seq_ID'].astype(int)
    kaiju_results = kaiju_fullTable[["kaiju_classified", "Seq_ID", "Tax_ID", "Seq_tax"]]

    ids1 = read_names_by_number(reads_file1, user_format)
    kaiju_fullTable["Seq_ID"] = kaiju_fullTable["Seq_ID"].map(ids1)
    kaiju_fullTable.to_csv(os.path.join(out_dir, 'kaiju_FormattedTable.txt'),
                           sep='\t', index=False)
    if os.path.isfile(os.path.join(out_dir, "kaiju_FormattedTable.txt.gz")):
        os.remove(os.path.join(out_dir, "kaiju_FormattedTable.txt.gz"))
    subprocess.check_call('gzip ' + os.path.join(out_dir, 'kaiju_FormattedTable.txt'),
                          shell=True)

    kodoja = pd.merge(kraken_results, kaiju_results, on='Seq_ID', how='outer')
    assert len(kraken_results) == len(kodoja), \
        'ERROR: Kraken and Kaiju results not merged properly'
    if hasattr(kodoja, 'sort_values'):
        # pandas 0.17 onwards
        kodoja.sort_values(['Seq_ID'], inplace=True)
    else:
        kodoja.sort(['Seq_ID'], inplace=True)
    kodoja.reset_index(drop=True, inplace=True)
    kodoja.rename(columns={"Seq_tax_x": "kraken_seq_tax", "Seq_tax_y": "kaiju_seq_tax",
                           'Tax_ID_x': 'kraken_tax_ID', 'Tax_ID_y': 'kaiju_tax_ID'}, inplace=True)

    kodoja["Seq_ID"] = kodoja["Seq_ID"].map(ids1)

    os.remove(os.path.join(out_dir, "kaiju_table.txt"))
    os.remove(os.path.join(out_dir, "kaiju_labels.txt"))
    os.remove(os.path.join(out_dir, "kraken_VRL.txt"))

    kodoja['combined_result'] = kodoja.kraken_tax_ID[kodoja['kraken_tax_ID'] == kodoja['kaiju_tax_ID']]
    if host_subset:
        kodoja = kodoja[(kodoja['kraken_tax_ID'] != float(host_subset)) &
                        (kodoja['kaiju_tax_ID'] != float(host_subset))]
    kodoja.to_csv(os.path.join(out_dir, 'kodoja_VRL.txt'),
                  sep='\t', index=False)

    def virusSummary(kodoja_data):
        """Merge tables to create summary table.

        Creates a summary table with virus species names, tax id, count of
        sequences by kraken, kaiju and sequences that were identified by both
        tools as belonging to that species.

        For each tax id, a sequence count for kraken, kaiju and the combined
        is made. '_levels' dict have all tax ids present in th table with the
        taxanomic 'labels' given by kraken-traslate.

        'associated_tax' dict, has tax ids which would be related to a species
        tax id, as they belong to taxa which are higher, and therefore if
        they could belong to a species but cannot be identified specifically
        (i.e. a sequence whih has been given the following label
        'd__Viruses|f__Closteroviridae|g__Ampelovirus' could be an unspecifically
        identified 'Grapevine_leafroll-associated_virus_4' the label for which is
        'd__Viruses|f__Closteroviridae|g__Ampelovirus|s__Grapevine_leafroll-associated_virus_4').
        """
        kraken_class = dict(kodoja_data['kraken_tax_ID'].value_counts())
        kraken_levels = pd.Series(kodoja_data.kraken_seq_tax.values,
                                  index=kodoja_data.kraken_tax_ID).to_dict()
        kaiju_class = dict(kodoja_data['kaiju_tax_ID'].value_counts())
        kaiju_levels = pd.Series(kodoja_data.kaiju_seq_tax.values,
                                 index=kodoja_data.kaiju_tax_ID).to_dict()

        # Number of sequences classified to taxID by both tools
        combined_class = dict(kodoja_data['combined_result'].value_counts())

        # Number of sequences classified to taxID by either tool
        either_class = kraken_class.copy()
        either_class.update(kaiju_class)
        either_class.pop(0, None)
        for key, value in either_class.items():
            if key in kraken_class:
                if key in kaiju_class:
                    either_class[key] = kraken_class[key] + kaiju_class[key]
                    if key in combined_class:
                        either_class[key] = either_class[key] - combined_class[key]
                else:
                    either_class[key] = kraken_class[key]
            else:
                either_class[key] = kaiju_class[key]

        levels_dict = kraken_levels.copy()
        levels_dict.update(kaiju_levels)
        levels_dict.pop(0, None)
        levels_dict = {k: levels_dict[k] for k in levels_dict if not isnan(k)}
        levels_tax = {key: list(map(str, value.split('|')))
                      for key, value in levels_dict.items()}

        LCA_tax = {}
        # Iterate over a copy of the values as we may remove taxonomy entries
        for key, tax in list(levels_tax.items()):
            if tax[-1][0] != 's':
                LCA_tax[key] = tax[-1]
                levels_tax.pop(key)

        species_dict = {}
        for key in levels_tax:
            species_dict[key] = " ".join(levels_tax[key][-1][3:].split("_"))

        # Find the genus for each species
        genus_per_species = {}
        for key, value in levels_dict.items():
            if len(value.split('g__')) > 1:
                genus_per_species[key] = value.split('g__')[1].split('|')[0]
            else:
                genus_per_species[key] = ''

        # TaxID for genus
        genus_taxid = {}
        for key, value in LCA_tax.items():
            if value[0:3] == 'g__':
                genus = value[3:]
                if genus in genus_taxid:
                    genus_taxid[genus].append(key)
                else:
                    genus_taxid[genus] = [key]
        with open(os.path.join(out_dir, 'genus_taxid.pkl'), 'wb') as pkl_dict:
            pickle.dump(genus_taxid, pkl_dict, protocol=pickle.HIGHEST_PROTOCOL)

        # Number of sequences classified to genus level
        def genus_seq_count(dict_class):
            genus_dict = {}
            for key, value in genus_taxid.items():
                seq_sum = 0
                for taxid in value:
                    if taxid in dict_class:
                        seq_sum += dict_class[taxid]
                genus_dict[key] = seq_sum
            return genus_dict

        genus_either = genus_seq_count(either_class)
        genus_combined = genus_seq_count(combined_class)

        table_summary = pd.DataFrame(columns=['Species', 'Species TaxID',
                                              'Species sequences',
                                              'Species sequences (stringent)',
                                              'Genus',
                                              'Genus sequences',
                                              'Genus sequences (stringent)'])
        table_summary['Species TaxID'] = [int(key) for key in levels_tax]
        table_summary['Species sequences'] = table_summary['Species TaxID'].map(either_class)
        table_summary['Species sequences (stringent)'] = table_summary['Species TaxID'].map(combined_class)
        table_summary['Species'] = table_summary['Species TaxID'].map(species_dict)
        table_summary['Genus'] = table_summary['Species TaxID'].map(genus_per_species)
        # Using functions in map to set default value of 0,
        # can use a defaultdict or Counter if have pandas 0.20 onwards
        table_summary['Genus sequences'] = table_summary['Genus'].map(lambda g: genus_either.get(g, 0))
        table_summary['Genus sequences (stringent)'] = table_summary['Genus'].map(lambda g: genus_combined.get(g, 0))
        if hasattr(table_summary, 'sort_values'):
            # pandas 0.17 onwards
            table_summary.sort_values(['Species sequences (stringent)', 'Species sequences'],
                                      ascending=False, inplace=True)
        else:
            table_summary.sort(['Species sequences (stringent)', 'Species sequences'],
                               ascending=False, inplace=True)
        table_summary.to_csv(os.path.join(out_dir, 'virus_table.txt'),
                             sep='\t', index=False)

    virusSummary(kodoja)
