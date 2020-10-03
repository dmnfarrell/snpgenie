#!/usr/bin/env python

"""
    snpgenie GUI.
    Created Jan 2020
    Copyright (C) Damien Farrell

    This program is free software; you can redistribute it and/or
    modify it under the terms of the GNU General Public License
    as published by the Free Software Foundation; either version 3
    of the License, or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, write to the Free Software
    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
"""

from __future__ import absolute_import, print_function
import sys,os,traceback,subprocess
import glob,platform,shutil
import pickle
import threading,time
from PySide2 import QtCore
from PySide2.QtWidgets import *
from PySide2.QtGui import *

import pandas as pd
import numpy as np
import pylab as plt
from Bio import SeqIO
from . import tools, aligners, app, widgets, tables, plotting, trees

home = os.path.expanduser("~")
module_path = os.path.dirname(os.path.abspath(__file__)) #path to module
logoimg = os.path.join(module_path, 'logo.png')

class App(QMainWindow):
    """GUI Application using PySide2 widgets"""
    def __init__(self, filenames=[], project=None):

        QMainWindow.__init__(self)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle("snpgenie")

        self.setWindowIcon(QIcon(logoimg))
        self.create_menu()
        self.main = QSplitter(self)
        #screen_resolution = QDesktopWidget().screenGeometry()
        screen = QGuiApplication.screens()[0]
        screen_resolution  = screen.geometry()
        if screen_resolution.height() > 1080:
            fac=0.8
            width, height = screen_resolution.width()*fac, screen_resolution.height()*fac
            self.setGeometry(QtCore.QRect(150, 150, width, height))
        else:
            self.showMaximized()

        self.main.setFocus()
        self.setCentralWidget(self.main)
        self.setup_gui()

        self.new_project()
        self.running = False

        if platform.system() == 'Windows':
            app.fetch_binaries()
        if project != None:
            self.load_project(project)
        self.threadpool = QtCore.QThreadPool()
        return

    def update_ref_genome(self):
        """Update the ref genome labels"""

        if self.ref_genome == None:
            refname=''
        else:
            refname = os.path.basename(self.ref_genome)
        if self.ref_gb == None:
            gbname = ''
        else:
            gbname = os.path.basename(self.ref_gb)
        self.reflabel.setText(refname)
        self.annotlabel.setText(gbname)
        return

    def setup_gui(self):
        """Add all GUI elements"""

        self.m = QSplitter(self.main)
        #left menu
        left = QWidget(self.m)
        l = QVBoxLayout(left)
        lbl = QLabel("Reference Genome:")
        l.addWidget(lbl)
        self.reflabel = QLabel()
        self.reflabel.setStyleSheet('color: blue')
        l.addWidget(self.reflabel)
        lbl = QLabel("Reference Annotation:")
        l.addWidget(lbl)
        self.annotlabel = QLabel()
        self.annotlabel.setStyleSheet('color: blue')
        l.addWidget(self.annotlabel)

        #create option widgets
        self.opts = AppOptions(parent=self.m)
        #optionswidget = QWidget(left)
        #l.addWidget(optionswidget)
        dialog = self.opts.showDialog(left, wrap=1, section_wrap=1)
        l.addWidget(dialog)

        l.addStretch()
        left.setFixedWidth(250)

        center = QWidget(self.m)
        l = QVBoxLayout(center)
        self.fastq_table = tables.FilesTable(center, app=self, dataframe=pd.DataFrame())
        l.addWidget(self.fastq_table)

        self.tabs = QTabWidget(center)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        l.addWidget(self.tabs)

        self.right = right = QWidget(self.m)
        l2 = QVBoxLayout(right)
        #mainlayout.addWidget(right)
        self.right_tabs = QTabWidget(right)
        self.right_tabs.setTabsClosable(True)
        self.right_tabs.tabCloseRequested.connect(self.close_right_tab)
        l2.addWidget(self.right_tabs)
        self.info = widgets.Editor(right, readOnly=True)
        font = QFont("Monospace")
        font.setPointSize(9)
        font.setStyleHint(QFont.TypeWriter)
        self.info.setFont(font)
        self.right_tabs.addTab(self.info, 'log')
        self.info.setText("Welcome")
        self.m.setSizes([50,200,150])
        self.m.setStretchFactor(1,0)

        self.statusBar = QStatusBar()
        from . import __version__
        self.projectlabel = QLabel('')
        self.projectlabel.setStyleSheet('color: blue')
        self.projectlabel.setAlignment(Qt.AlignLeft)
        self.statusBar.addWidget(self.projectlabel, 1)
        lbl = QLabel("Output folder:")
        self.statusBar.addWidget(lbl,1)
        lbl.setAlignment(Qt.AlignRight)
        self.outdirLabel = QLabel("")
        self.statusBar.addWidget(self.outdirLabel, 1)
        self.outdirLabel.setAlignment(Qt.AlignLeft)
        self.outdirLabel.setStyleSheet('color: blue')

        self.progressbar = QProgressBar()
        self.progressbar.setRange(0,1)
        self.statusBar.addWidget(self.progressbar, 3)
        self.progressbar.setAlignment(Qt.AlignRight)
        self.setStatusBar(self.statusBar)
        return

    @QtCore.Slot(int)
    def close_tab(self, index):
        """Close current tab"""

        #index = self.tabs.currentIndex()
        name = self.tabs.tabText(index)
        self.tabs.removeTab(index)
        return

    @QtCore.Slot(int)
    def close_right_tab(self, index):
        """Close right tab"""

        name = self.right_tabs.tabText(index)
        if name == 'log':
            return
        self.right_tabs.removeTab(index)
        return

    def create_menu(self):
        """Create the menu bar for the application. """

        self.file_menu = QMenu('&File', self)
        #self.file_menu.addAction('&New', self.newProject,
        #        QtCore.Qt.CTRL + QtCore.Qt.Key_N)
        self.file_menu.addAction('&Add Folder', self.load_fastq_folder_dialog,
                QtCore.Qt.CTRL + QtCore.Qt.Key_F)
        self.file_menu.addAction('&Add Fastq Files', self.load_fastq_files_dialog,
                QtCore.Qt.CTRL + QtCore.Qt.Key_A)
        #self.file_menu.addAction('&Load Test Files', self.load_test,
        #        QtCore.Qt.CTRL + QtCore.Qt.Key_T)
        self.menuBar().addSeparator()
        self.file_menu.addAction('&New Project', lambda: self.new_project(ask=True),
                QtCore.Qt.CTRL + QtCore.Qt.Key_N)
        self.file_menu.addAction('&Open Project', self.load_project_dialog,
                QtCore.Qt.CTRL + QtCore.Qt.Key_O)
        self.file_menu.addAction('&Save Project', self.save_project,
                QtCore.Qt.CTRL + QtCore.Qt.Key_S)
        self.file_menu.addAction('&Save Project As', self.save_project_dialog)
        self.file_menu.addAction('&Quit', self.quit,
                QtCore.Qt.CTRL + QtCore.Qt.Key_Q)
        self.menuBar().addMenu(self.file_menu)

        self.analysis_menu = QMenu('&Analysis', self)
        self.menuBar().addSeparator()
        self.menuBar().addMenu(self.analysis_menu)
        #self.analysis_menu.addAction('&Run Blast',
        #    lambda: self.run_threaded_process(self.run_gene_finder, self.find_genes_completed))
        self.analysis_menu.addAction('&Trim Reads',
            lambda: self.run_threaded_process(self.run_trimming, self.processing_completed))
        self.analysis_menu.addAction('&Align Reads',
            lambda: self.run_threaded_process(self.align_files, self.alignment_completed))
        self.analysis_menu.addAction('&Call Variants',
            lambda: self.run_threaded_process(self.variant_calling, self.processing_completed))
        self.analysis_menu.addAction('&Create SNP alignment',
            lambda: self.run_threaded_process(self.snp_alignment, self.processing_completed))
        self.analysis_menu.addAction('&Run Workflow', self.run)
        self.analysis_menu.addSeparator()
        self.analysis_menu.addAction('&Show Annotation', self.show_ref_annotation)

        self.settings_menu = QMenu('&Settings', self)
        self.menuBar().addMenu(self.settings_menu)
        self.settings_menu.addAction('&Set Output Folder', self.set_output_folder)
        self.settings_menu.addAction('&Set Reference Sequence', self.set_reference)
        self.settings_menu.addAction('&Set Annnotation (genbank)', self.set_annotation)
        self.settings_menu.addAction('&Add Sample Meta Data', self.merge_meta_data)
        self.settings_menu.addAction('&Clean Up Files', self.clean_up)

        self.presets_menu = QMenu('&Load Preset', self)
        self.menuBar().addMenu(self.presets_menu)
        self.load_presets_menu()

        self.tools_menu = QMenu('&Tools', self)
        self.menuBar().addMenu(self.tools_menu)
        self.tools_menu.addAction('&Fastq Qualities Report', self.fastq_quality_report)
        self.tools_menu.addAction('&RD Analysis (MTBC)',
            lambda: self.run_threaded_process(self.rd_analysis, self.rd_analysis_completed))

        self.help_menu = QMenu('&Help', self)
        self.menuBar().addMenu(self.help_menu)
        self.help_menu.addAction('&Help', self.online_documentation)
        self.help_menu.addAction('&About', self.about)

    def load_presets_menu(self):
        """Add preset genomes to menu"""

        genomes = {'Mbovis AF212297':{'sequence':app.mbovis_genome, 'gb':app.mbovis_gb},
                   'MTB H37Rv':{'sequence':app.mtb_genome, 'gb':app.mtb_gb}}
        for name in genomes:
            seqname = genomes[name]['sequence']
            gbfile = genomes[name]['gb']
            def func(seqname,gbfile):
                self.set_reference(seqname)
                self.set_annotation(gbfile)
            receiver = lambda seqname=seqname, gb=gbfile: func(seqname, gb)
            self.presets_menu.addAction('&%s' %name, receiver)
        return

    def save_project(self):
        """Save project"""

        if self.proj_file == None:
            self.save_project_dialog()

        filename = self.proj_file
        data={}
        data['inputs'] = self.fastq_table.getDataFrame()
        keys = ['outputdir','results','ref_genome','ref_gb']
        for k in keys:
            if hasattr(self, k):
                data[k] = self.__dict__[k]

        self.projectlabel.setText(filename)
        pickle.dump(data, open(filename,'wb'))
        return

    def save_project_dialog(self):
        """Save as project"""

        options = QFileDialog.Options()
        filename, _ = QFileDialog.getSaveFileName(self,"Save Project",
                                                  "","Project files (*.snpgenie);;All files (*.*)",
                                                  options=options)
        if filename:
            if not os.path.splitext(filename)[1] == '.snpgenie':
                filename += '.snpgenie'
            self.proj_file = filename
            self.save_project()
        return

    def new_project(self, ask=False):
        """Clear all loaded inputs and results"""

        reply=None
        if ask == True:
            reply = QMessageBox.question(self, 'Confirm', "This will clear the current project.\nAre you sure?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            return False

        self.outputdir = None
        self.sheets = {}
        self.results = {}
        self.proj_file = None
        self.fastq_table.setDataFrame(pd.DataFrame({'name':[]}))
        self.tabs.clear()
        self.ref_genome = None
        self.ref_gb = None
        self.projectlabel.setText('')
        self.outdirLabel.setText(self.outputdir)
        self.update_ref_genome()
        return

    def load_project(self, filename=None):
        """Load project"""

        self.new_project()
        data = pickle.load(open(filename,'rb'))
        keys = ['sheets','outputdir','results','ref_genome','ref_gb']
        for k in keys:
            if k in data:
                self.__dict__[k] = data[k]

        ft = self.fastq_table
        ft.setDataFrame(data['inputs'])
        ft.resizeColumns()
        self.update_ref_genome()
        self.proj_file = filename
        self.projectlabel.setText(self.proj_file)
        self.outdirLabel.setText(self.outputdir)
        print (self.results)
        if 'vcf_file' in self.results:
            self.show_variants()
        return

    def load_project_dialog(self):
        """Load project"""

        filename, _ = QFileDialog.getOpenFileName(self, 'Open Project', './',
                                        filter="Project Files(*.snpgenie);;All Files(*.*)")
        if not filename:
            return
        if not os.path.exists(filename):
            print ('no such file')
        self.load_project(filename)
        return

    def load_test(self):
        """Load test_files"""

        reply = self.new_project(ask=True)
        if reply == False:
            return
        #filenames = glob.glob(os.path.join(app.datadir, '*.fa'))
        self.load_fastq_table(filenames)
        return

    def check_missing_files(self):
        """Check folders for missing files"""

        folders = ['mapped','trimmed']
        #for f in folders:

        return

    def clean_up(self):
        """Clean up intermediate files"""

        msg = 'This will remove all intermediate files in the output folder. Proceed?'
        reply = QMessageBox.question(self, 'Warning!', msg,
                                        QMessageBox.No | QMessageBox.Yes )
        if reply == QMessageBox.No:
            return

        folders = ['mapped','trimmed']
        for l in folders:
            files = glob.glob(os.path.join(self.outputdir, l, '*'))
            print (files)
            for f in files:
                os.remove(f)
        bcf = os.path.join(self.outputdir, 'raw.bcf')
        if os.path.exists(bcf):
             os.remove(bcf)
        return

    def load_fastq_table(self, filenames):
        """Append/Load fasta inputs into table"""

        if filenames is None or len(filenames) == 0:
            return

        df = self.fastq_table.model.df
        new = app.get_samples(filenames)
        new['read_length'] = new.filename.apply(tools.get_fastq_info)

        if len(df)>0:
            new = pd.concat([df,new],sort=False).reset_index(drop=True)
            new = new.drop_duplicates('filename')
        self.fastq_table.setDataFrame(new)
        self.fastq_table.resizeColumns()
        return

    def load_fastq_folder_dialog(self):
        """Load fastq folder"""

        path = QFileDialog.getExistingDirectory(self, 'Add Input Folder', './')
        if not path:
            return
        filenames = app.get_files_from_paths(path)
        self.load_fastq_table(filenames)
        return

    def load_fastq_files_dialog(self):
        """Load fastq files"""

        filenames, _ = QFileDialog.getOpenFileNames(self, 'Open File', './',
                                                    filter="Fastq Files(*.fq *.fastq *.fq.gz *.fastq.gz);;All Files(*.*)")
        if not filenames:
            return
        self.load_fastq_table(filenames)
        return

    def set_reference(self, filename=None):
        """Reset the reference sequence"""

        msg = "This will change the reference genome. You will need to re-run any previous alignments. Are you sure?"
        reply = QMessageBox.question(self, 'Warning!', msg,
                                        QMessageBox.No | QMessageBox.Yes )
        if reply == QMessageBox.No:
            return
        if filename == None:
            filter="Fasta Files(*.fa *.fna *.fasta)"
            filename, _ = QFileDialog.getOpenFileName(self, 'Open File', './',
                                        filter="%s;;All Files(*.*)" %filter)
            if not filename:
                return
        self.ref_genome = filename
        self.update_ref_genome()
        return

    def set_annotation(self, filename=None):

        if filename == None:
            filename = self.add_file("Genbank Files(*.gb *.gbk *.gbff)")
        self.ref_gb = filename
        #put annotation in a dataframe
        self.annot = tools.genbank_to_dataframe(self.ref_gb)
        self.update_ref_genome()
        return

    def merge_meta_data(self):
        """Add sample meta data by merging with file table"""

        filename, _ = QFileDialog.getOpenFileName(self, 'Open File', './',
                                    filter="Text Files(*.csv *.txt *.tsv);;All Files(*.*)")
        if not filename:
            return

        df = self.fastq_table.model.df
        meta = pd.read_csv(filename)


        new = df.merge(meta, left_on='sample', right_on='ACCESSION',how='left')
        self.fastq_table.setDataFrame(new)
        return

    def add_file(self, filter="Fasta Files(*.fa *.fna *.fasta)", path=None):
        """Add a file to the config folders"""

        filename, _ = QFileDialog.getOpenFileName(self, 'Open File', './',
                                    filter="%s;;All Files(*.*)" %filter)
        if not filename:
            return
        if path != None:
            #copy file
            if not os.path.exists(path):
                os.makedirs(path)
            dest = os.path.join(path, os.path.basename(filename))
            shutil.copy(filename, dest)
            self.show_info('added %s' %filename)
        return filename

    def set_output_folder(self):
        """Set the output folder"""

        selected_directory = QFileDialog.getExistingDirectory()
        if selected_directory:
            self.outputdir = selected_directory
        #check it's empty?
        self.outdirLabel.setText(self.outputdir)
        return

    def check_output_folder(self):
        """check if we have an output dir"""

        if self.outputdir == None:
            #QMessageBox.warning(self, 'No output folder set',
            #    'You should set an output folder from the Settings menu')
            self.show_info('You should set an output folder from the Settings menu')
            return 0
        return 1

    def run_trimming(self, progress_callback):
        """Run quality and adapter trimming"""

        retval = self.check_output_folder()
        if retval == 0:
            return
        progress_callback.emit('Running trimming')
        self.opts.applyOptions()
        kwds = self.opts.kwds
        self.running = True
        overwrite = kwds['overwrite']
        threshold = kwds['quality']
        df = self.fastq_table.model.df
        path = os.path.join(self.outputdir, 'trimmed')
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        st=time.time()
        for i,row in df.iterrows():
            outfile = os.path.join(path, os.path.basename(row.filename))
            progress_callback.emit(outfile)
            if not os.path.exists(outfile) or overwrite == True:
                tools.trim_reads(row.filename, outfile)
            df.loc[i,'trimmed'] = outfile
            self.fastq_table.refresh()
        t = round(time.time()-st,1)
        progress_callback.emit('took %s seconds' %str(t))
        return

    def align_files(self, progress_callback):
        """Run gene annotation for input files.
        progress_callback: signal for indicating progress in gui
        """

        retval = self.check_output_folder()
        if retval == 0:
            return
        if self.ref_genome == None:
            self.show_info('no reference genome!')
            return
        self.running = True
        self.opts.applyOptions()
        kwds = self.opts.kwds
        overwrite = kwds['overwrite']
        df = self.fastq_table.model.df
        #rows = self.fastq_table.getSelectedRows()
        #df = df.loc[rows]
        msg = 'Aligning reads..\nThis may take some time.'
        progress_callback.emit(msg)
        ref = self.ref_genome
        aligners.build_bwa_index(ref)

        progress_callback.emit('Using reference genome: %s' %ref)
        path = os.path.join(self.outputdir, 'mapped')
        if not os.path.exists(path):
            os.makedirs(path)
        app.align_reads(df, idx=ref, outdir=path, overwrite=overwrite, threads=kwds['threads'],
                            callback=progress_callback.emit)
        return

    def variant_calling(self, progress_callback=None):
        """Run variant calling for available bam files."""

        retval = self.check_output_folder()
        if retval == 0:
            return
        self.running = True
        self.opts.applyOptions()
        kwds = self.opts.kwds
        #print (kwds)
        overwrite = kwds['overwrite']
        threads = int(kwds['threads'])
        filters = kwds['filters']
        df = self.fastq_table.model.df
        path = self.outputdir

        gff_file = os.path.join(path, self.ref_gb+'.gff')
        tools.gff_bcftools_format(self.ref_gb, gff_file)
        #use trimmed files if present in table
        bam_files = list(df.bam_file.unique())

        self.results['vcf_file'] = app.variant_calling(bam_files, self.ref_genome, path,
                                    threads=threads,
                                    overwrite=overwrite, filters=filters,
                                    gff_file=gff_file,
                                    callback=progress_callback.emit)
        csqmat = self.results['csq_matrix'] = os.path.join(self.outputdir, 'csq.matrix')
        return

    def show_variants(self):

        vcf_file = self.results['vcf_file']
        vdf = tools.vcf_to_dataframe(vcf_file)
        table = tables.DefaultTable(self.tabs, app=self, dataframe=vdf)
        i = self.tabs.addTab(table, 'variants')
        if 'csq_matrix' in self.results:
            csqmat = pd.read_csv(self.results['csq_matrix'])
            table = tables.DefaultTable(self.tabs, app=self, dataframe=csqmat)
            i = self.tabs.addTab(table, 'csq.matrix')
            self.tabs.setCurrentIndex(i)
        return

    def snp_alignment(self, progress_callback):
        """Make snp matrix from variant positions"""

        self.opts.applyOptions()
        kwds = self.opts.kwds
        vcf_file = self.results['vcf_file']
        progress_callback.emit('Making SNP alignment')
        result, smat = tools.fasta_alignment_from_vcf(vcf_file, self.ref_genome,
                                                callback=progress_callback.emit)
        print (result)
        outfile = os.path.join(self.outputdir, 'core.fa')
        self.results['snp_file'] = outfile
        SeqIO.write(result, outfile, 'fasta')
        return

    def view_tree(self):

        trees.run_RAXML(outfile)
        #t = trees.create_tree('RAxML_bipartitions.variants')#, labelmap)
        trees.biopython_draw_tree('RAxML_bipartitions.variants')
        return

    def processing_completed(self):
        """Generic process completed"""

        self.info.append("finished")
        self.progressbar.setRange(0,1)
        self.running = False
        return

    def alignment_completed(self):
        """Alignment/calling completed"""

        self.info.append("finished")
        self.progressbar.setRange(0,1)
        df = self.fastq_table.getDataFrame()
        self.fastq_table.refresh()
        self.running = False
        return

    def run(self):
        """Run all steps"""

        self.run_threaded_process(self.run_trimming, self.processing_completed)
        return

    def run_threaded_process(self, process, on_complete):
        """Execute a function in the background with a worker"""

        if self.running == True:
            return
        worker = Worker(fn=process)
        self.threadpool.start(worker)
        worker.signals.finished.connect(on_complete)
        worker.signals.progress.connect(self.progress_fn)
        self.progressbar.setRange(0,0)
        return

    def progress_fn(self, msg):

        print (msg)
        self.info.append(msg)
        self.info.verticalScrollBar().setValue(1)
        return

    def show_ref_annotation(self):
        """Show annotation in table"""

        gb_file = self.ref_gb
        df = tools.genbank_to_dataframe(gb_file)
        t = tables.DataFrameTable(self.tabs, dataframe=df)
        i = self.tabs.addTab(t, 'ref_annotation')
        self.tabs.setCurrentIndex(i)
        return

    def quality_summary(self, row):
        """Summary of a single fastq file"""

        df = self.fastq_table.model.df
        row = self.fastq_table.getSelectedRows()[0]
        data = df.iloc[row]
        name = 'qual:'+data['name']
        if name in self.get_tab_names():
            return
        w = widgets.PlotViewer(self)
        fig,ax = plt.subplots(2,1, figsize=(7,5), dpi=65, facecolor=(1,1,1), edgecolor=(0,0,0))
        axs=ax.flat
        if not os.path.exists(data.filename):
            self.show_info('This file is missing.')
            return
        tools.plot_fastq_qualities(data.filename, ax=axs[0])
        tools.plot_fastq_gc_content(data.filename, ax=axs[1])
        plt.tight_layout()
        w.show_figure(fig)
        i = self.tabs.addTab(w, name )
        self.tabs.setCurrentIndex(i)
        return

    def show_bam_viewer(self, row):
        """Show simple alignment view for a bam file"""

        df = self.fastq_table.model.df
        row = self.fastq_table.getSelectedRows()[0]
        data = df.iloc[row]
        name = 'aln:'+data['name']
        if name in self.get_tab_names():
            return
        #text view using samtools tview
        w = widgets.SimpleBamViewer(self)
        w.load_data(data.bam_file, self.ref_genome, self.ref_gb)
        w.redraw(xstart=1)
        i = self.tabs.addTab(w, name )
        self.tabs.setCurrentIndex(i)
        return

    def fastq_quality_report(self):
        """Make fastq quality report as pdf"""

        if self.running == True:
            print ('another process running')
            return
        self.running == True
        df = self.fastq_table.model.df
        out = os.path.join(self.outputdir,'qc_report.pdf')
        if not os.path.exists(out):
            def func(progress_callback):
                tools.pdf_qc_reports(df.filename, out)
                import webbrowser
                webbrowser.open_new(out)
            self.run_threaded_process(func, self.processing_completed)
        else:
                import webbrowser
                webbrowser.open_new(out)
        return

    def rd_analysis(self, progress_callback):
        """Run RD analysis for MTBC species"""

        self.running == True
        self.opts.applyOptions()
        kwds = self.opts.kwds
        from . import rdiff
        rdiff.create_rd_index()
        df = self.fastq_table.model.df
        out = os.path.join(self.outputdir,'rd_analysis')
        res = rdiff.find_regions(df, out, threads=kwds['threads'],
                                 callback=progress_callback.emit)
        self.rd_result = res
        return

    def rd_analysis_completed(self):
        """Alignment/calling completed"""

        self.info.append("finished")
        self.progressbar.setRange(0,1)
        res = self.rd_result
        from . import rdiff
        X = rdiff.get_matrix(res, cutoff=0.15)
        X['species'] = X.apply(rdiff.apply_rules,1)
        fig,ax = plt.subplots(1,1)
        plotting.plot_matrix(X.set_index('species',append=True), cmap='cubehelix',ax=ax)

        table = tables.DefaultTable(self.tabs, app=self, dataframe=res)
        self.tabs.addTab(table, 'RD analysis')
        #add plot
        w = widgets.PlotViewer(self)
        w.show_figure(fig)
        i = self.tabs.addTab(w, 'RD')

        self.running = False
        return

    def show_info(self, msg):

        self.info.append(msg)
        self.info.verticalScrollBar().setValue(
            self.info.verticalScrollBar().maximum())
        return

    def get_tab_names(self):
        return {self.tabs.tabText(index):index for index in range(self.tabs.count())}

    def quit(self):
        self.close()
        return

    def closeEvent(self, event=None):

        if self.proj_file != None and event != None:
            reply = QMessageBox.question(self, 'Confirm', "Save the current project?",
                                            QMessageBox.Cancel | QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.Yes:
                self.save_project()
        #self.close()
        event.accept()

    def _check_snap(self):
        if os.environ.has_key('SNAP_USER_COMMON'):
            print ('running inside snap')
            return True
        return False

    def online_documentation(self,event=None):
        """Open the online documentation"""

        import webbrowser
        link='https://github.com/dmnfarrell/btbgenie'
        webbrowser.open(link,autoraise=1)
        return

    def about(self):

        from . import __version__
        import matplotlib
        import PySide2
        pandasver = pd.__version__
        pythonver = platform.python_version()
        mplver = matplotlib.__version__
        qtver = PySide2.QtCore.__version__
        if self._check_snap == True:
            snap='(snap)'
        else:
            snap=''

        text='snpgenie GUI\n'\
            +'version '+__version__+snap+'\n'\
            +'Copyright (C) Damien Farrell 2020-\n'\
            +'This program is free software; you can redistribute it and/or '\
            +'modify it under the terms of the GNU GPL '\
            +'as published by the Free Software Foundation; either '\
            +'version 3 of the License, or (at your option) any '\
            +'later version.\n'\
            +'Using Python v%s, PySide2 v%s\n' %(pythonver, qtver)\
            +'pandas v%s, matplotlib v%s' %(pandasver,mplver)

        msg = QMessageBox.about(self, "About", text)
        return

#https://www.learnpyqt.com/courses/concurrent-execution/multithreading-pyqt-applications-qthreadpool/
class Worker(QtCore.QRunnable):
    """Worker thread for running background tasks."""

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.kwargs['progress_callback'] = self.signals.progress

    @QtCore.Slot()
    def run(self):
        try:
            result = self.fn(
                *self.args, **self.kwargs,
            )
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()

class WorkerSignals(QtCore.QObject):
    """
    Defines the signals available from a running worker thread.
    Supported signals are:
    finished
        No data
    error
        `tuple` (exctype, value, traceback.format_exc() )
    result
        `object` data returned from processing, anything
    """
    finished = QtCore.Signal()
    error = QtCore.Signal(tuple)
    result = QtCore.Signal(object)
    progress = QtCore.Signal(str)

class AppOptions(widgets.BaseOptions):
    """Class to provide a dialog for global plot options"""

    def __init__(self, parent=None):
        """Setup variables"""
        self.parent = parent
        self.kwds = {}
        genomes = []
        aligners = ['bwa','bowtie','bowtie2']
        cpus = [str(i) for i in range(1,os.cpu_count()+1)]
        self.groups = {'general':['threads','overwrite'],
                        #'reference':['refgenome','annotation'],
                        'trimming':['quality'],
                        'aligners':['aligner'],
                        'variant calling':['filters'],
                        'blast':['db','identity','coverage'],
                       }
        self.opts = {'threads':{'type':'combobox','default':4,'items':cpus},
                    'overwrite':{'type':'checkbox','default':False},
                    #'refgenome':{'type':'combobox','default':'',
                    #'items':genomes,'label':'genome'},
                    #'annotation':{'type':'combobox','default':'',
                    #'items':[],'label':'annotation'},
                    'aligner':{'type':'combobox','default':'bwa',
                    'items':aligners,'label':'aligner'},
                    'db':{'type':'combobox','default':'card',
                    'items':[],'label':'database'},
                    'filters':{'type':'entry','default':app.default_filter},
                    'identity':{'type':'entry','default':90},
                    'coverage':{'type':'entry','default':50},
                    'quality':{'type':'spinbox','default':30}
                    }
        return

def main():
    "Run the application"

    import sys, os
    from argparse import ArgumentParser
    parser = ArgumentParser(description='snpgenie gui tool')
    parser.add_argument("-f", "--fasta", dest="filenames",default=[],
                        help="input fasta file", metavar="FILE")
    parser.add_argument("-p", "--proj", dest="project",default=None,
                        help="load .snpgenie project file", metavar="FILE")
    args = vars(parser.parse_args())

    app = QApplication(sys.argv)
    aw = App(**args)
    aw.show()
    app.exec_()

if __name__ == '__main__':
    main()
