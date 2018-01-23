import ROOT, socket, os, shutil, subprocess
from math import pi
#
# Get plot directory
#
plotDir = os.path.expandvars('/eos/user/t/tomc/www/ttG/' if 'lxp' in socket.gethostname() else '/user/$USER/www/ttG/')
def getResultsFile(*args):
  return os.path.join(*((plotDir,)+args+('results.pkl',)))

#
# Get object (e.g. hist) from file using key
#
def getObjFromFile(fname, hname):
    f = ROOT.TFile(fname)
    assert not f.IsZombie()
    f.cd()
    htmp = f.Get(hname)
    if not htmp:  return htmp
    ROOT.gDirectory.cd('PyROOT:/')
    res = htmp.Clone()
    f.Close()
    return res

#
# Copy the index.php file to plotting directory
#
def copyIndexPHP(directory):
  index_php = os.path.join(directory, 'index.php' )
  if not os.path.exists(directory): os.makedirs(directory)
  if not directory[-1] == '/': directory = directory+'/'
  subdirs = directory.split('/')
  for i in range(1,len(subdirs)):
    p = '/'.join(subdirs[:-i])
    if not (p.count('plots') or p.count('ttG')): continue
    index_php = os.path.join(p, 'index.php')
    shutil.copyfile(os.path.expandvars( '$CMSSW_BASE/src/ttg/tools/php/index.php'), index_php)

#
# Update the latest git information
#
def updateGitInfo():
  os.system('(git log -n 1;git diff) &> git.txt')

#
# Copy git info for plot
#
def copyGitInfo(path):
  if os.path.isfile('git.txt'):
    shutil.copyfile('git.txt', path)


#
# Edit the info file in a given path
#
def editInfo(path):
  editor = os.getenv('EDITOR', 'vi')
  subprocess.call('%s %s' % (editor, os.path.join(path, 'info.txt')), shell=True)


#
# Delta phi function
#
def deltaPhi(phi1, phi2):
  dphi = phi2-phi1
  if dphi > pi:   dphi -= 2.0*pi
  if dphi <= -pi: dphi += 2.0*pi
  return abs(dphi)
