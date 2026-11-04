#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import division

import os, re, sys, argparse

#------------------------------------------------------------------------------#
parser = argparse.ArgumentParser(prog='m4cm_animation',
                                 description='This script uses the "m4cm.py" script to create the initial PNG/JPG files which requires "convert" from ImageMagick and then makes use of "Mencoder" (packaged together with Mplayer) to render the animation from the loose PNG/JPG pictures.',
                                 epilog='May the Foruce be with you...')
#------------------------------------------------------------------------------#

#------------------------------------------------------------------------------#
parser.add_argument('-d', '--delete',
                    action='store_true',
                    dest='DELETE_PICS',
                    default=True,
                    help='delete PNG/JPG files after converting to MPNG, MPG or AVI')
parser.add_argument('-f', '--fps',
                    action='store',
                    dest='fps',
                    type=int,          #stores argument as an 'int'
                    nargs='?',         #use only one arguments or the default value
                    metavar='FPS',
                    default=10,
                    help='the frames per second of the movie file')
parser.add_argument('-o', '--output_type',
                    action='store',
                    dest='output_type',
                    type=str,          #stores argument as a 'str'
                    nargs='?',         #use only one arguments or the default value
                    choices=['mpng','MPNG','mpg','MPG','avi','AVI'],
                    metavar='OUTPUT_TYPE',
                    default='mpg',
                    help='the output type of the movie file [MPNG|MPG|AVI]')
parser.add_argument('-r', '--resolution',
                    action='store',
                    dest='resolution',
                    type=int,          #stores argument as an 'int'
                    nargs='?',         #use only one arguments or the default value
                    metavar='RESOLUTION',
                    default=300,
                    help='PNG or JPG resolution (or density)')
parser.add_argument('--start',
                    action='store',
                    dest='start',
                    type=int,          #stores argument as an 'int'
                    nargs='?',         #use only one arguments or the default value
                    metavar='START',
                    default=0,
                    help='the start angle value for "_wet" variable in the .m4cm file i.e. "$\omega_e t$" in LaTeX')
parser.add_argument('--stop',
                    action='store',
                    dest='stop',
                    type=int,          #stores argument as an 'int'
                    nargs='?',         #use only one arguments or the default value
                    metavar='STOP',
                    default=360,
                    help='the stop angle value for "_wet" variable in the .m4cm file i.e. "$\omega_e t$" in LaTeX')
parser.add_argument('--step',
                    action='store',
                    dest='step',
                    type=int,          #stores argument as an 'int'
                    nargs='?',         #use only one arguments or the default value
                    metavar='STEP',
                    default=5,
                    help='the step angle value for "_wet" variable in the .m4cm file i.e. "$\omega_e t$" in LaTeX')
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
try:
  (m4cmFileName, m4cmFileExt) = os.path.splitext(args.m4cmFile[0])
except:
  parser.print_help()
  parser.error('An OptionParser error occurred...!')

m4cm_file_lines=file(m4cmFileName+m4cmFileExt,'r').readlines()

wet_range=range(args.start,args.stop+args.step,args.step)

for i,wt in enumerate(wet_range):
  for line_no, line in enumerate(m4cm_file_lines):
    if re.search(r'\s*_wet\s*=',line):
        m4cm_file_lines.pop(line_no)
        m4cm_file_lines.insert(line_no,'_wet=%d\n' % wt)
        break
  file(m4cmFileName+'.m4','w').writelines(m4cm_file_lines)
  print "Processing: %d of %d" % (i+1,len(wet_range))
  if args.output_type.lower()=='mpng':
    os.system('m4cm -n -r %d -d -q -a _%03d %s' % (args.resolution,wt,m4cmFileName+'.m4'))
  if args.output_type.lower()=='avi' or 'mpg':
    os.system('m4cm -j -r %d -d -Q -a _%03d %s' % (args.resolution,wt,m4cmFileName+'.m4'))

if args.output_type.lower()=='mpng':
  os.system('mencoder mf://%s -mf fps=%d:type=png -ovc copy -nosound -o %s' % (m4cmFileName+'_*.png',args.fps,m4cmFileName+'.'+args.output_type))
if args.output_type.lower()=='mpg':
  os.system('mencoder mf://%s -mf type=jpg:fps=%d -ovc lavc -lavcopts vcodec=msmpeg4v2:mbd=2:trell -nosound -o %s' % (m4cmFileName+'_*.jpg',args.fps,m4cmFileName+'.'+args.output_type))
if args.output_type.lower()=='avi':
  os.system('mencoder mf://%s -mf type=jpg:fps=%d -ovc lavc -lavcopts vcodec=mpeg4:mbd=2:trell -nosound -o %s' % (m4cmFileName+'_*.jpg',args.fps,m4cmFileName+'.'+args.output_type))

if args.DELETE_PICS: 
  if args.output_type.lower()=='mpng':
    rmdelext='png'
  else:
    rmdelext='jpg'
    
  if sys.platform == 'win32':
    os.system('del %s' % m4cmFileName+'.m4')
    os.system('del %s' % m4cmFileName+'_*.'+rmdelext)
  else:
    os.system('del %s' % m4cmFileName+'.m4')
    os.system('del %s' % m4cmFileName+'_*.'+rmdelext)

print "\nDone!"


