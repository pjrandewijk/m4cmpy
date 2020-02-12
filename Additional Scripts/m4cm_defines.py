#!/usr/bin/python3

#Extracts the M4 Circuit Macros as defined in the "defines.tex" LaTeX file https://ece.uwaterloo.ca/~aplevich/Circuit_macros/ for syntax highlighting purposes to be used in Kate/Kile, Notepad++ and Programmer's Notepad 2

import re

pattern=r'\\macrodef\{([A-Za-z0-9\\_]*)\}.*\n'

macros=[]
i=0

for line in open('./defines/defines.tex','r').readlines():
  match=re.search(pattern,line)
  if match:
    macros.append(match.group(1))
    i+=1
    
print("%g M4 circuit macros found" % i)

f1=open('./defines/m4cm_defines_katepart.txt','w')
f2=open('./defines/m4cm_defines_notepad++.txt','w')
f3=open('./defines/m4cm_defines_pnotepad2.txt','w')

for macro in macros:
  tmp=re.sub(r'\\','',macro)
  f1.write('<item> '+tmp+' </item>\n')
  f2.write(tmp+'\n')
  f3.write(tmp+' ')

f1.close()
f2.close()
f3.close()
