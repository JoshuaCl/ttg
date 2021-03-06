#! /usr/bin/env python

#
# Script to create additional variables in the trees and reduce it to manageable size
#


#
# Argument parser and logging
#
import os, argparse
argParser = argparse.ArgumentParser(description = "Argument parser")
argParser.add_argument('--logLevel',       action='store',      default='INFO',               help='Log level for logging', nargs='?', choices=['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'TRACE'])
argParser.add_argument('--sample',         action='store',      default=None,                 help='Sample for which to produce reducedTuple, as listed in samples/data/tuples.conf')
argParser.add_argument('--type',           action='store',      default='eleSusyLoose-phoCB', help='Specify type of reducedTuple')
argParser.add_argument('--subJob',         action='store',      default=None,                 help='The xth subjob for a sample, number of subjobs is defined by split parameter in tuples.conf')
argParser.add_argument('--splitData',      action='store',      default=None,                 help='Splits the data in its separate runs')
argParser.add_argument('--QCD',            action='store_true', default=False,                help='use tuplesQCD.conf instead of tuples.conf')
argParser.add_argument('--singleLep',      action='store_true', default=False,                help='use tuplesSingleLep.conf instead of tuples.conf')
argParser.add_argument('--runLocal',       action='store_true', default=False,                help='use local resources instead of Cream02')
argParser.add_argument('--debug',          action='store_true', default=False,                help='only run over first three files for debugging')
argParser.add_argument('--dryRun',         action='store_true', default=False,                help='do not launch subjobs, only show them')
argParser.add_argument('--isChild',        action='store_true', default=False,                help='mark as subjob, will never submit subjobs by itself')
argParser.add_argument('--overwrite',      action='store_true', default=False,                help='overwrite if valid output file already exists')
args = argParser.parse_args()


from ttg.tools.logger import getLogger
log = getLogger(args.logLevel)

#
# Create sample list
#
from ttg.samples.Sample import createSampleList,getSampleFromList
if args.QCD:         tuples = 'tuplesQCD.conf'
elif args.singleLep: tuples = 'tuplesSingleLep.conf'
else:                tuples = 'tuples.conf'
sampleList = createSampleList(os.path.expandvars('$CMSSW_BASE/src/ttg/samples/data/' + tuples))

#
# Submit subjobs: for each sample split in args.splitJobs
#
if not args.isChild and not args.subJob:
  from ttg.tools.jobSubmitter import submitJobs
  if args.sample: sampleList = filter(lambda s: s.name == args.sample, sampleList)

  jobs = []
  for sample in sampleList:
    if (args.type.count('Scale') or args.type.count('Res')) and (sample.name.count('isr') or sample.name.count('fsr')): continue

    if sample.isData:
      runs = ['B','C','D','E','F','G','H'] # Chains become very slow for data, so we split them
      if args.splitData in runs: splitData = [args.splitData]
      else:                      splitData = runs
    else:                        splitData = [None]
    jobs += [(sample.name, str(i), j) for i in xrange(sample.splitJobs) for j in splitData]

  submitJobs(__file__, ('sample','subJob','splitData'), jobs, argParser, subLog=args.type)
  exit(0)

#
# From here on we are in the subjob, first init the chain and the lumiWeight
#

import ROOT
ROOT.gROOT.SetBatch(True)

sample = getSampleFromList(sampleList, args.sample)
c      = sample.initTree(skimType=('singlePhoton' if args.QCD else 'dilepton'), shortDebug=args.debug, splitData=args.splitData)

if not sample.isData:
  lumiWeights  = [(float(sample.xsec)*1000/totalWeight) for totalWeight in sample.getTotalWeights()]


#
# Create new reduced tree
#
reducedTupleDir = os.path.join('/user/tomc/public/reducedTuples', sample.productionLabel, args.type, sample.name)
try:    os.makedirs(reducedTupleDir)
except: pass

outputId   = (args.splitData if args.splitData in ['B','C','D','E','F','G','H'] else '') + str(args.subJob)
outputName = os.path.join(reducedTupleDir, sample.name + '_' + outputId + '.root')
from ttg.tools.helpers import isValidRootFile
if not args.overwrite and isValidRootFile(outputName):
  log.info('Finished: valid outputfile already exists')
  exit(0)
outputFile = ROOT.TFile(outputName ,"RECREATE")
outputFile.cd()

#
# Switch off unused branches, avoid copying of branches we want to delete
#
unusedBranches = ["HLT","Flag","HN","tau","Ewk","lMuon","miniIso","WOIso","leptonMva","closest","_pt","decay"]
deleteBranches = ["Scale","Res","pass","flag","met","POG"]
if not sample.isData:
  unusedBranches += ["gen_nL", "gen_l","gen_met","gen_HT"]
  deleteBranches += ["heWeight","gen_ph"]
for i in unusedBranches + deleteBranches: sample.chain.SetBranchStatus("*"+i+"*", 0)
outputTree = sample.chain.CloneTree(0)
for i in deleteBranches: sample.chain.SetBranchStatus("*"+i+"*", 1)


#
# Initialize reweighting functions
#
from ttg.reduceTuple.puReweighting import getReweightingFunction
puReweighting     = getReweightingFunction(data="PU_2016_36000_XSecCentral")
puReweightingUp   = getReweightingFunction(data="PU_2016_36000_XSecUp")
puReweightingDown = getReweightingFunction(data="PU_2016_36000_XSecDown")

from ttg.reduceTuple.leptonTrackingEfficiency import leptonTrackingEfficiency
from ttg.reduceTuple.leptonSF import leptonSF as leptonSF_
from ttg.reduceTuple.photonSF import photonSF as photonSF_
from ttg.reduceTuple.triggerEfficiency import triggerEfficiency
from ttg.reduceTuple.btagEfficiency import btagEfficiency
leptonTrackingSF = leptonTrackingEfficiency()
leptonSF         = leptonSF_()
photonSF         = photonSF_()
triggerEff       = triggerEfficiency()
btagSF           = btagEfficiency()


#
# Define new branches
#
newBranches  = ['ph/I','ph_pt/F','phJetDeltaR/F','matchedGenPh/I', 'matchedGenEle/I', 'nphotons/I']
newBranches += ['njets/I','j1/I','j2/I','nbjets/I','ndbjets/I']
newBranches += ['l1/I','l2/I','looseLeptonVeto/O','l1_pt/F','l2_pt/F']
newBranches += ['mll/F','mllg/F','ml1g/F','ml2g/F','phL1DeltaR/F','phL2DeltaR/F']

if args.singleLep: newBranches += ['isE/O','isMu/O']
elif not args.QCD: newBranches += ['isEE/O','isMuMu/O','isEMu/O']

if not sample.isData:
  for sys in ['JECUp', 'JECDown', 'JERUp', 'JERDown']:        newBranches += ['njets_' + sys + '/I', 'nbjets_' + sys + '/I', 'ndbjets_' + sys +'/I', 'j1_' + sys + '/I', 'j2_' + sys + '/I']
  for sys in ['', 'Up', 'Down']:                              newBranches += ['lWeight' + sys + '/F', 'puWeight' + sys + '/F', 'triggerWeight' + sys + '/F', 'phWeight' + sys + '/F']
  for sys in ['', 'lUp', 'lDown', 'bUp', 'bDown']:            newBranches += ['bTagWeightCSV' + sys + '/F', 'bTagWeight' + sys + '/F']
  for sys in ['q2Up','q2Down','q2ShapeUp', 'q2ShapeDown']:    newBranches += ['weight_' + sys + '/F']
  for sys in ['pdfUp','pdfDown','pdfShapeUp','pdfShapeDown']: newBranches += ['weight_' + sys + '/F']
  newBranches += ['genWeight/F', 'lTrackWeight/F']
  newBranches += ['genPhDeltaR/F','genPhPassParentage/O','genPhMinDeltaR/F','genPhRelPt/F','genPhPt/F','genPhEta/F']
  newBranches += ['prefireCheck/O']

from ttg.tools.makeBranches import makeBranches
from ttg.reduceTuple.objectSelection import setIDSelection, selectLeptons, selectPhotons, makeInvariantMasses, goodJets, bJets, makeDeltaR, prefireRemoval
newVars = makeBranches(outputTree, newBranches)

setIDSelection(c, args.type)
minLeptons            = 0 if args.QCD else (1 if args.singleLep else 2)
doPhotonCut           = args.type.count('pho')
jetPtCut              = 40 if args.type.count('jetPt40') else 30

def switchBranches(c, default, variation):
  return lambda c: setattr(c, default, getattr(c, variation))

branchModifications = []
for var in ['ScaleUp','ScaleDown','ResUp','ResDown']:
  if args.type.count('e'  + var): branchModifications += [switchBranches(c, '_lPtCorr',  '_lPt' + var),  switchBranches(c, '_lECorr',  '_lE' + var)]
  if args.type.count('ph' + var): branchModifications += [switchBranches(c, '_phPtCorr', '_phPt' + var), switchBranches(c, '_phECorr', '_phE' + var)]

#
# Loop over the tree and make new vars
#
log.info('Starting event loop')
from math import sqrt
for i in sample.eventLoop(totalJobs=sample.splitJobs, subJob=int(args.subJob), selectionString='_lheHTIncoming<100' if sample.name.count('HT0to100') else None):
  c.GetEntry(i)
  for s in branchModifications: s(c)

  if not selectLeptons(c, newVars, minLeptons):                                              continue
  if not selectPhotons(c, newVars, doPhotonCut, minLeptons, sample.isData):                  continue

  if minLeptons > 1:
    if sample.isData:
      if not c._passMETFiltersData:                                                          continue
      if sample.name.count('DoubleMuon') and not c._passTTG_mm:                              continue
      if sample.name.count('DoubleEG')   and not c._passTTG_ee:                              continue
      if sample.name.count('MuonEG')     and not c._passTTG_em:                              continue
      if sample.name.count('SingleMuon'):
        if newVars.isMuMu and not (not c._passTTG_mm and c._passTTG_m):                      continue
        if newVars.isEMu  and not (not c._passTTG_em and c._passTTG_m):                      continue
      if sample.name.count('SingleElectron'):
        if newVars.isEE   and not (not c._passTTG_ee and c._passTTG_e):                      continue
        if newVars.isEMu  and not (not c._passTTG_em and c._passTTG_e and not c._passTTG_m): continue
    else:
      if not c._passMETFiltersMC:                                                            continue
      if newVars.isEE   and not (c._passTTG_ee or c._passTTG_e):                             continue
      if newVars.isEMu  and not (c._passTTG_em or c._passTTG_e or c._passTTG_m):             continue
      if newVars.isMuMu and not (c._passTTG_mm or c._passTTG_m):                             continue

  if minLeptons == 1:
    if sample.isData:
      if sample.name.count('SingleMuon')     and newVars.isMu and not c._passTTG_m:          continue
      if sample.name.count('SingleElectron') and newVars.isE  and not c._passTTG_e:          continue
    else:
      if newVars.isMu and not c.passTTG_m:                                                   continue
      if newVars.isE  and not c.passTTG_e:                                                   continue

  goodJets(c, newVars, jetPtCut)
  bJets(c, newVars)
  makeInvariantMasses(c, newVars)
  makeDeltaR(c, newVars)

  if not sample.isData:
    newVars.genWeight           = c._weight*lumiWeights[0]
    newVars.prefireCheck        = prefireRemoval(c)

    try:    q2Weights           = [c._lheWeight[i]*lumiWeights[i] for i in [1,2,3,4,6,8]]  # See https://twiki.cern.ch/twiki/bin/view/CMS/TopSystematics#Factorization_and_renormalizatio and https://twiki.cern.ch/twiki/bin/viewauth/CMS/LHEReaderCMSSW for order (index 0->id 1001, etc...)
    except: q2Weights           = [newVars.genWeight]
    newVars.weight_q2Down       = c._weight*min(q2Weights)
    newVars.weight_q2Up         = c._weight*max(q2Weights)

    try:    q2Weights           = [c._lheWeight[i]*lumiWeights[0] for i in [1,2,3,4,6,8]]  # See https://twiki.cern.ch/twiki/bin/view/CMS/TopSystematics#Factorization_and_renormalizatio and https://twiki.cern.ch/twiki/bin/viewauth/CMS/LHEReaderCMSSW for order (index 0->id 1001, etc...)
    except: q2Weights           = [newVars.genWeight]
    newVars.weight_q2ShapeDown  = c._weight*min(q2Weights)
    newVars.weight_q2ShapeUp    = c._weight*max(q2Weights)

    try:    pdfVarRms           = sqrt(sum([(lumiWeights[0] - c._lheWeight[i]*lumiWeights[i])**2 for i in range(9,109)])/100)   # Using RMS of 100 pdf's
    except: pdfVarRms           = 0
    newVars.weight_pdfDown      = c._weight*(lumiWeights[0] - pdfVarRms)
    newVars.weight_pdfUp        = c._weight*(lumiWeights[0] + pdfVarRms)

    try:    pdfVarRms           = sqrt(sum([(1 - c._lheWeight[i])**2 for i in range(9,109)])/100)   # Using RMS of 100 pdf's
    except: pdfVarRms           = 0
    newVars.weight_pdfShapeDown = newVars.genWeight*(1 - pdfVarRms)
    newVars.weight_pdfShapeUp   = newVars.genWeight*(1 + pdfVarRms)

    newVars.puWeight            = puReweighting(c._nTrueInt)
    newVars.puWeightUp          = puReweightingUp(c._nTrueInt)
    newVars.puWeightDown        = puReweightingDown(c._nTrueInt)

    if minLeptons > 1:
      l1 = newVars.l1
      l2 = newVars.l2
      newVars.lWeight           = leptonSF.getSF(c, l1)*leptonSF.getSF(c, l2)
      newVars.lWeightUp         = leptonSF.getSF(c, l1, sigma=+1)*leptonSF.getSF(c, l2, sigma=+1)
      newVars.lWeightDown       = leptonSF.getSF(c, l1, sigma=-1)*leptonSF.getSF(c, l2, sigma=-1)
      newVars.lTrackWeight      = leptonTrackingSF.getSF(c, l1)*leptonTrackingSF.getSF(c, l2)
    elif minLeptons > 0:
      l1 = newVars.l1
      newVars.lWeight           = leptonSF.getSF(c, l1)
      newVars.lWeightUp         = leptonSF.getSF(c, l1, sigma=+1)
      newVars.lWeightDown       = leptonSF.getSF(c, l1, sigma=-1)
      newVars.lTrackWeight      = leptonTrackingSF.getSF(c, l1)
    else:
      newVars.lWeight           = 1.
      newVars.lWeightUp         = 1.
      newVars.lWeightDown       = 1.
      newVars.lTrackWeight      = 1.

    newVars.phWeight            = photonSF.getSF(c, newVars.ph) if len(c.photons) > 0 else 1
    newVars.phWeightUp          = photonSF.getSF(c, newVars.ph, sigma=+1) if len(c.photons) > 0 else 1
    newVars.phWeightDown        = photonSF.getSF(c, newVars.ph, sigma=-1) if len(c.photons) > 0 else 1

    # method 1a
    for sys in ['', 'lUp', 'lDown', 'bUp', 'bDown']:
      setattr(newVars, 'bTagWeightCSV' + sys, btagSF.getBtagSF_1a(sys, c, c.bjets, isCSV = True))
      setattr(newVars, 'bTagWeight'    + sys, btagSF.getBtagSF_1a(sys, c, c.bjets, isCSV = False))

    trigWeight, trigErr        = triggerEff.getSF(c, l1, l2) if minLeptons > 1 else (1., 0.)
    newVars.triggerWeight      = trigWeight
    newVars.triggerWeightUp    = trigWeight+trigErr
    newVars.triggerWeightDown  = trigWeight-trigErr

  outputTree.Fill()
outputTree.AutoSave()

if not sample.isData:
  trueIntHist = sample.getTrueInteractions()
  outputFile.cd()
  trueIntHist.Write('nTrue')
outputFile.Close()
log.info('Finished')
