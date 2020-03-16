#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import glob
import subprocess
import argparse

__version__ = 3.2

#------------------------------------------------------------------------------#
parser = argparse.ArgumentParser(prog='M4CM',
                                 description='M4CM is used to create standalone PDF/JPG/PNG figures for M4 Circuit Macros.',
                                 epilog='Instead of "M4CM_FILE", it is also possible to use "*.m4cm" to compile all the ".m4cm" files in the current folder.')
#------------------------------------------------------------------------------#

#------------------------------------------------------------------------------#
parser.add_argument('-a', '--append',
                    action='store',     #stores argument (default action)
                    dest='append',      #name of the stored argument (i.e append chars)
                    type=str,           #stores argument as a 'string'
                    nargs='?',          #use only one arguments or the default value
                    metavar='APPEND_CHARS',
                    default='',
                    help='Character/String to append to the end of the output file(s)')
parser.add_argument('-b', '--boundingbox_offset',
                    action='store',
                    dest='BB_offset',
                    type=int,           #stores arguments as 'integers' in the list
                    nargs=4,           #use only one arguments or the default value
                    metavar=('L','B','R','T'),
                    default=(1,1,1,1),
                    help='the BoundingBox Offset: left offset point value, top offset point value, right offset point value, bottom offset point values, the default is: 1 1 1 1, i.e. 1pt in each direction')
parser.add_argument('-d', '--delete_eps',
                    action='store_true',
                    dest='DELETE_EPS',
                    help='delete EPS file after converting to PNG or PDF')
parser.add_argument('-e', '--eps',
                    action='store_true',
                    dest='EPS',
                    default=True,
                    help='convert to EPS format [default option]')
parser.add_argument('-g', '--ghostscript',
                    action='store_true',
                    dest='GS',
                    default=False,
                    help='use GhostScript to convert to PNG/JPG format')
parser.add_argument('-j', '--jpg',
                    action='store_true',
                    dest='JPG',
                    default=False,
                    help='convert to JPG format')
parser.add_argument('-n', '--png',
                    action='store_true',
                    dest='PNG',
                    default=False,
                    help='convert to PNG format')
parser.add_argument('-o', '--output_dir',
                    action='store',
                    dest='output_dir',
                    type=str,           #stores argument as a 'string'
                    nargs='?',          #use only one arguments or the default value
                    metavar='OUTPUT_DIR',
                    default='',
                    help='the Output Directory for the EPS/PDF/PNG/JPG output files')
parser.add_argument('-p', '--pdf',
                    action='store_true',
                    dest='PDF',
                    help='convert to PDF format')
parser.add_argument('-q', '--quiet',
                    action='store_true',
                    dest='QUIET',
                    default=False,
                    help='run quietly, but print progress')
parser.add_argument('-Q', '--super_quiet',
                    action='store_true',
                    dest='SUPER_QUIET',
                    default=False,
                    help='run quietly with no output')
parser.add_argument('-r', '--resolution',
                    action='store',
                    dest='resolution',
                    type=int,           #stores argument as an 'int'
                    nargs='?',          #use only one arguments or the default value
                    metavar='PNG_RESOLUTION',
                    default=600,
                    help='PNG or JPG resolution (or density)')
parser.add_argument('-t', '--template',
                    action='store',     #stores argument (default action)
                    dest='template',    #name of the stored argument (i.e template file)
                    type=str,           #stores argument as a 'string'
                    nargs='?',          #use only one arguments or the default value
                    metavar='LATEX_TEMPLATE_FILE',
                    default='default.ltx',
                    help='LaTeX template file to be used [default="default.ltx"]')

parser.add_argument('-v','--version',
                    action='version',
                    version='Version: %(prog)s '+str(__version__))                    

parser.add_argument('m4cmFile',
                    nargs='*',
                    metavar='M4CM_FILE',
                    help='M4CM File to be compiled')

#------------------------------------------------------------------------------#
args =parser.parse_args()

if len(args.m4cmFile)==0:
  parser.print_help()
  exit()
  
#------------------------------------------------------------------------------#
if not os.path.exists(args.template):
  parser.print_help()
  raise OSError('LATEX_TEMPLATE_FILE, %s, could not be found...' % args.template)

if re.search(r'%dpic_pstricks_output_here%',open(args.template, encoding='utf-8').read(),re.MULTILINE)==None:
  parser.print_help()
  raise 'The "%dpic_pstricks_output_here%" tag in the LATEX_TEMPLATE_FILE could not be found...'
  
#------------------------------------------------------------------------------#
m4cmFileNameList=[]
if re.search(r'\*',args.m4cmFile[0]) or re.search(r'\?',args.m4cmFile[0]):
  args.m4cmFile=glob.glob(args.m4cmFile[0])
for each_m4cmFileName in args.m4cmFile:
  try:
    (m4cmFileName, m4cmFileExt) = os.path.splitext(each_m4cmFileName)
    m4cmFileNameList.append(m4cmFileName)
  except:
    parser.print_help()
    parser.error('An OptionParser error occurred...!')

for filename in m4cmFileNameList:
  if not args.SUPER_QUIET: print('\nProcessing: '+filename+m4cmFileExt)
  if os.path.exists(filename+m4cmFileExt):
    ###########################################################################
    #Parsing with M4 Circuit Macros to generate PIC code
    ###########################################################################
    if not args.SUPER_QUIET: print('m4cm -> pic')
    m4_cmd=['m4',filename+m4cmFileExt]
    filename=filename+args.append
    m4_subprocess=subprocess.Popen(m4_cmd,stdout=subprocess.PIPE)

    ###########################################################################
    #Compiling the PIC code to pstricks output
    ###########################################################################
    if not args.SUPER_QUIET: print('pic -> pstricks')
    dpic_cmd='dpic -p'
    dpic_subprocess=subprocess.Popen(dpic_cmd,stdin=m4_subprocess.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True)

    ###########################################################################
    #Wrapping M4CM_FILE with the LATEX_TEMPLATE_FILE
    ###########################################################################
    if not args.SUPER_QUIET: print('wrapping the '+filename+'.tex with '+args.template)
    tmpl_lst=open(args.template, encoding='utf-8').readlines()
    dpic_out,dpic_err=dpic_subprocess.communicate()
    if dpic_err:
      raise NameError(dpic_err)
      break
    tex_lst=dpic_out.decode('utf-8').splitlines()
    for i in range(len(tmpl_lst)):
      if re.search(r'%dpic_pstricks_output_here%',tmpl_lst[i]):
        tmpl_lst.pop(i)
        for j in range(len(tex_lst)):
            tmpl_lst.insert(i+j,tex_lst[j]+'\n')
        break

    #Create Output Directory if required
    cwd=os.getcwd()
    if args.output_dir!='':
      if not os.path.exists(args.output_dir):
        os.mkdir(args.output_dir)
      os.chdir(args.output_dir)

    open(filename+'.ltx','w', encoding='utf-8').writelines(tmpl_lst)

    ###########################################################################
    #Creating a DVI output using LaTeX
    ###########################################################################
    if not args.SUPER_QUIET: print('pstricks -> dvi')
    latex_cmd='latex '
    if args.QUIET or args.SUPER_QUIET:
      if sys.platform=='win32':
        latex_cmd+='-quiet '
      else:
        latex_cmd+='-interaction=batchmode '
    latex_cmd+=filename+'.ltx'
    if sys.platform!='win32' and args.SUPER_QUIET:
      latex_cmd+=' 1> /dev/null 2>&1'
    latex_err=os.system(latex_cmd)
    if latex_err:
      print('LaTeX found errors in '+filename+'.ltx')
      if args.QUIET or args.SUPER_QUIET:
        print('To find out what the problem was, run the program without the "-q"/"--quiet" or "-Q/"--super_quiet option"...\n')
      else:
        print('\n')
      sys.exit(1)

    #Delete all the LaTeX files
    if os.path.exists(filename+'.aux'):
      os.remove(filename+'.aux')
    if os.path.exists(filename+'.log'):
      os.remove(filename+'.log')
    if os.path.exists(filename+'.out'):
      os.remove(filename+'.out')
    if os.path.exists(filename+'.ltx'):
      os.remove(filename+'.ltx')

    ###########################################################################
    #Converting the DVI output to PostScript
    ###########################################################################

    if not args.SUPER_QUIET: print('dvi -> ps')
    if args.QUIET or args.SUPER_QUIET:
      dvips_cmd=['dvips','-j0','-G0','-Ppdf','-Pdownload35','-q',filename+'.dvi']
    else:
      dvips_cmd=['dvips','-j0','-G0','-Ppdf','-Pdownload35',filename+'.dvi']
    dvips_subprocess=subprocess.Popen(dvips_cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding='utf-8')
    dvips_out, dvips_err=dvips_subprocess.communicate() #'dvips_out' contains the error messages, if any
    if dvips_out:
      print('DVIPS Error:')
      print(dvips_err)
      #break
    os.remove(filename+'.dvi')
    
    ###########################################################################
    #Converting the PS file to an EPS file
    ###########################################################################
	
    #First step: Obtain the Bounding Box information using Ghostscript
    if not args.SUPER_QUIET: print('ps -> eps')
    gs_exe='gswin64c' if sys.platform=='win32' else 'gs' 
    gs_cmd = '%s -dBATCH -dNOPAUSE -sDEVICE=bbox "%s"' %  (gs_exe, filename+'.ps')
    gs_subprocess=subprocess.Popen(gs_cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True,encoding='utf-8')
    gs_out, gs_err = gs_subprocess.communicate() #'gs_err' contains the actual Bounding Box information and not the 'gs_out'
    if not args.QUIET: print(gs_out)
    BB_match=re.search(r'(%%BoundingBox:)\s+([0-9]*)\s+([0-9]*)\s+([0-9]*)\s+([0-9]*)',gs_err)
    HRBB_match=re.search(r'(%%HiResBoundingBox:)\s+([0-9\.]*)\s+([0-9\.]*)\s+([0-9\.]*)\s+([0-9\.]*)',gs_err)
	
    #Second step: The manual convertion process
    ps_file_lst=open(filename+'.ps','r').readlines()    
    ps_file_lst.pop(0)
    ps_file_lst.insert(0,'%!PS-Adobe-3.0 EPSF-3.0\n')
    for line_no, line in enumerate(ps_file_lst):
      if re.search(r'%%BoundingBox:',line):    #Expand the BoundingBox by 1pt in each direction
        ps_file_lst.pop(line_no)
        ps_file_lst.insert(line_no,'''%s %d %d %d %d
%s %.6f %.6f %.6f %.6f\n''' % (BB_match.group(1), int(BB_match.group(2))-args.BB_offset[0],
                                                  int(BB_match.group(3))-args.BB_offset[1],
                                                  int(BB_match.group(4))+args.BB_offset[2],
                                                  int(BB_match.group(5))+args.BB_offset[3],
                               HRBB_match.group(1), float(HRBB_match.group(2))-args.BB_offset[0],
                                                    float(HRBB_match.group(3))-args.BB_offset[1],
                                                    float(HRBB_match.group(4))+args.BB_offset[2],
                                                    float(HRBB_match.group(5))+args.BB_offset[3]))
      elif re.search(r'%%EndComments',line):
        i=line_no
        ps_file_lst.insert(line_no,'''%%BeginProlog
save
countdictstack
mark
newpath
/showpage {} def
/setpagedevice {pop} def
%%EndProlog
%%Page 1 1\n''')
        break
#      elif re.search(r'%%Bound',line) or re.search(r'%%HiResBound',line) or re.search(r'%%DocumentMedia',line) or re.search(r'%%Pages',line) or re.search(r'%%PageBoundingBox',line):    
#        ps_file_lst.pop(line_no)
    #Insert just before the '%%EOF' line:
    i=len(ps_file_lst)-1
    ps_file_lst.insert(i,'''cleartomark
countdictstack
exch sub { end } repeat
restore\n''') 
  
    open(filename+'.eps','w').writelines(ps_file_lst)
    os.remove(filename+'.ps')

    ###########################################################################
    #Creating a PNG output, if required
    ###########################################################################
    if args.PNG:
      if not args.SUPER_QUIET: print('eps -> png')
      if args.GS:
        #Using Ghostsript
        #Checking for platform
        if sys.platform == 'win32':
          ps_exe =  'gswin64c'
        else:
          ps_exe = 'gs'
        if args.QUIET or args.SUPER_QUIET:
          pngwrite_cmd='%s -dQUIET -dBATCH -dNOPAUSE -dSAFER -dEPSCrop -dGraphicsAlphaBits=4 -sDEVICE=pngalpha -r%d -sOutputFile=%s.png %s.eps' % (ps_exe, args.resolution, filename, filename)
        else:
          pngwrite_cmd='%s -dBATCH -dNOPAUSE -dSAFER -dEPSCrop -dGraphicsAlphaBits=4 -sDEVICE=pngalpha -r%d -sOutputFile=%s.png %s.eps' % (ps_exe, args.resolution, filename, filename)
      else:
        #Using ImageMagick's convert instead of Ghostsript
        pngwrite_cmd='magick convert -density %d %s.eps %s.png' % (args.resolution, filename, filename)

      pngwrite_err=os.system(pngwrite_cmd)
      if pngwrite_err:
        print('Error executing: '+pngwrite_cmd)
        break

    ###########################################################################
    #Creating a JPG output, if required
    ###########################################################################
    if args.JPG:
      if not args.SUPER_QUIET: print('eps -> jpg')
      if args.GS:
        #Using Ghostsript
        #Checking for platform
        if sys.platform == 'win32':
          ps_exe =  'gswin64c'
        else:
          ps_exe = 'gs'
        if args.QUIET or args.SUPER_QUIET:
          jpgwrite_cmd='%s -dQUIET -dBATCH -dNOPAUSE -dSAFER -dEPSCrop -dGraphicsAlphaBits=4 -sDEVICE=jpeg -r%d -dJPEGQ=75 -sOutputFile=%s.jpg %s.eps' % (ps_exe, args.resolution, filename, filename)
        else:
          jpgwrite_cmd='%s -dBATCH -dNOPAUSE -dSAFER -dEPSCrop -dGraphicsAlphaBits=4 -sDEVICE=jpeg -r%d -dJPEGQ=75 -sOutputFile=%s.jpg %s.eps' % (ps_exe, args.resolution, filename, filename)
      else:
        #Using ImageMagick's convert instead of Ghostsript
        jpgwrite_cmd='magick convert -density %d %s.eps %s.jpg' % (args.resolution,filename,filename)
      
      jpgwrite_err=os.system(jpgwrite_cmd)
      if jpgwrite_err:
        print('Error executing: '+jpgwrite_cmd)
        break

    ###########################################################################
    #Creating a PDF output, if required
    ###########################################################################
    if args.PDF:
      if not args.SUPER_QUIET: print('eps -> pdf')
      eps2pdf_cmd='epstopdf '+filename+'.eps'
      eps2pdf_err=os.system(eps2pdf_cmd)
      if eps2pdf_err:
        print('Error executing: '+eps2pdf_cmd)
        break

    #Delete EPS file if required
    if (args.PNG or args.JPG or args.PDF) and args.DELETE_EPS:
      os.remove(filename+'.eps')
    
    if not args.SUPER_QUIET:
      print('Done!')
    
    os.chdir(cwd)

  else:
    print(filename+m4cmFileExt+' was not found...?')
