from ttg.tools.logger import getLogger
log = getLogger()

#
# Plot class
# Still messy, contains a lot of functions, but does a lot of automatized work
#
import ROOT, os, uuid, numpy, math
import cPickle as pickle
from math import sqrt
from ttg.tools.helpers import copyIndexPHP, copyGitInfo, plotDir, addHist
from ttg.tools.lock import lock
from ttg.tools.style import drawTex, getDefaultCanvas

#
# Apply the relative variation between source and sourceVar to the destination histogram
#
def applySysToOtherHist(source, sourceVar, destination):
  destinationVar = destination.Clone()
  for i in range(source.GetNbinsX()+1):
    modificationFactor = 1.+(source.GetBinContent(i)-sourceVar.GetBinContent(i))/source.GetBinContent(i) if source.GetBinContent(i) > 0 else 1.
    destinationVar.SetBinContent(i, modificationFactor*destination.GetBinContent(i))
  return destinationVar

#
# Load a histogram from pkl
#
loadedPkls = {}
def getHistFromPkl(subdirs, plotName, sys, *selectors):
  global loadePkls
  hist = None
  resultFile = os.path.join(*((plotDir,)+subdirs+(plotName +'.pkl',)))
  if os.path.isdir(os.path.dirname(resultFile)):
    if resultFile not in loadedPkls:
      with lock(resultFile, 'rb') as f: loadedPkls[resultFile] = pickle.load(f)
    for selector in selectors:
      filtered = {s:h for s,h in loadedPkls[resultFile][plotName+sys].iteritems() if all(s.count(sel) for sel in selector)}
      if len(filtered) == 1:   hist = addHist(hist, filtered[filtered.keys()[0]])
      elif len(filtered) > 1:  log.error('Multiple possibilities to look for ' + str(selector) + ': ' + str(filtered.keys()))
  else:                        log.error('Missing cache file ' + resultFile)
  if 'Scale' in sys and not any('MuonEG' in sel for sel in selectors):
    data    = getHistFromPkl(subdirs, plotName, '',   ['MuonEG'],['DoubleEG'],['DoubleMuon'])
    dataSys = getHistFromPkl(subdirs, plotName, sys,  ['MuonEG'],['DoubleEG'],['DoubleMuon'])
    hist = applySysToOtherHist(data, dataSys, hist)
  if not hist: log.error('Missing ' + str(selectors) + ' for plot ' + plotName + ' in ' + resultFile)
  return hist

#
# Get systematic uncertainty on sideband template: based on shape difference of ttbar hadronicFakes in sideband and nominal region
#
def applySidebandUnc(hist, plot, resultsDir, up):
  selection     = resultsDir.split('/')[-1]
  ttbarNominal  = getHistFromPkl(('sigmaIetaIeta-ttpow-hadronicFake-bins-central', 'all', selection), plot, '', ['TTJets','hadronicFake','pass'])
  ttbarSideband = getHistFromPkl(('sigmaIetaIeta-ttpow-hadronicFake-bins-central', 'all', selection), plot, '', ['TTJets','hadronicFake,0.012'])
  ttbarNominal.Scale(1/ttbarNominal.Integral())
  ttbarSideband.Scale(1/ttbarSideband.Integral())
  if up: return applySysToOtherHist(ttbarNominal, ttbarSideband, hist)
  else:  return applySysToOtherHist(ttbarSideband, ttbarNominal, hist)

#
# Returns histmodificator which applies labels to x-axis
#
def xAxisLabels(labels):
  def applyLabels(h):
    for i,l in enumerate(labels):
      h.GetXaxis().SetBinLabel(i+1, l)
  return [applyLabels]

#
# Normalize binwidth when non-unifor bin width is used
#
def normalizeBinWidth(hist, norm=None):
  if norm:
    for i in range(hist.GetXaxis().GetNbins()+1):
      val   = hist.GetBinContent(i)
      err   = hist.GetBinError(i)
      width = hist.GetBinWidth(i)
      hist.SetBinContent(i, val/(width/norm))
      hist.SetBinError(i, err/(width/norm))


#
# Function which fills all plots and removes them when the lamdbda fails (e.g. because var is not defined)
#
def fillPlots(plots, c, sample, eventWeight):
  removePlots = False
  for plot in plots:
    try:
      plot.fill(sample, eventWeight)
    except:
      if removePlots: toRemove.append(plot)
      else:           toRemove = [plot]
      removePlots = True
      log.info('Not considering plot ' + plot.name + ' for this selection')
  if removePlots:
    for p in toRemove: plots.remove(p)
    toRemove = []


#
# Plot class
#
class Plot:
  defaultStack        = None
  defaultTexY         = None
  defaultOverflowBin  = None
  defaultNormBinWidth = None

  @staticmethod
  def setDefaults(stack = None, texY="Events", overflowBin='upper'):
      Plot.defaultStack        = stack
      Plot.defaultTexY         = texY
      Plot.defaultOverflowBin  = overflowBin

  def __init__(self, name, texX, varX, binning, stack=None, texY=None, overflowBin='default', normBinWidth='default', histModifications=[]):
    self.stack             = stack        if stack else Plot.defaultStack
    self.texY              = texY         if texY else Plot.defaultTexY
    self.overflowBin       = overflowBin  if overflowBin!='default'  else Plot.defaultOverflowBin
    self.normBinWidth      = normBinWidth if normBinWidth!='default' else Plot.defaultNormBinWidth
    self.name              = name
    self.texX              = texX
    self.varX              = varX
    self.histModifications = histModifications
    self.scaleFactor       = None

    if type(binning)==type([]):   self.binning = (len(binning)-1, numpy.array(binning))
    elif type(binning)==type(()): self.binning = binning

    self.histos = {}
    for s in sum(self.stack, []):
      name           = self.name + s.name
      self.histos[s] = ROOT.TH1F(name, name, *self.binning)


  #
  # Add an overflow bin, optionally called from the draw function
  #
  def addOverFlowBin1D(self, histo, addOverFlowBin = None):
    if addOverFlowBin and not hasattr(histo, 'overflowApplied'):
      if addOverFlowBin.lower() == "upper" or addOverFlowBin.lower() == "both":
          nbins = histo.GetNbinsX()
          histo.SetBinContent(nbins, histo.GetBinContent(nbins) + histo.GetBinContent(nbins + 1))
          histo.SetBinError(nbins, sqrt(histo.GetBinError(nbins)**2 + histo.GetBinError(nbins + 1)**2))
      if addOverFlowBin.lower() == "lower" or addOverFlowBin.lower() == "both":
          histo.SetBinContent(1, histo.GetBinContent(0) + histo.GetBinContent(1))
          histo.SetBinError(1, sqrt(histo.GetBinError(0)**2 + histo.GetBinError(1)**2))
      histo.overflowApplied = True

  def fill(self, sample, weight=1.):
    self.histos[sample].Fill(self.varX(sample.chain), weight)

  #
  # Stacking the hist, called during the draw function
  #
  def stackHists(self, histsToStack, sorting=True):
    # Merge if texName is the same
    for i in range(len(histsToStack)):
      if not histsToStack[i]: continue
      for j in range(i+1, len(histsToStack)):
        if not histsToStack[j]: continue
        if histsToStack[i].texName == histsToStack[j].texName:
          histsToStack[i].Add(histsToStack[j])
          histsToStack[j] = None
    histsToStack = [h for h in histsToStack if h]

    if sorting: histsToStack.sort(key=lambda h  : -h.Integral())

    # Add up stacks
    for i, h in enumerate(histsToStack):
      for j in range(i+1, len(histsToStack)):
        histsToStack[i].Add(histsToStack[j])

    if h.legendStyle != 'f': return histsToStack[:1] # do not show sub-contributions when line or errorstyle
    else:                    return histsToStack


  #
  # Scaling options, optionally called from the draw function
  #
  def scaleStacks(self, histos, scaling):
    if scaling=="unity":
      for stack in histos:
        if not stack[0].Integral() > 0: continue
        if self.normBinWidth: factor = 1./stack[0].Integral('width') # actually not fully correct for figures with overflow bin, should check
        else:                 factor = 1./stack[0].Integral()
        for h in stack: h.Scale(factor)
    else:
      if not isinstance(scaling, dict):
        raise ValueError( "'scaling' must be of the form {0:1, 2:3} which normalizes stack[0] to stack[1] etc. Got '%r'" % scaling )
      for source, target in scaling.iteritems():
        if not (isinstance(source, int) and isinstance(target, int) ):
          raise ValueError( "Scaling should be {0:1, 1:2, ...}. Expected ints, got %r %r"%( source, target ) )

        source_yield = histos[source][0].Integral()

        if source_yield == 0:
          log.warning( "Requested to scale empty Stack? Do nothing." )
          continue

        self.scaleFactor = histos[target][0].Integral()/source_yield
        for h in histos[source]: h.Scale(self.scaleFactor)
        if len(scaling) == 1: return [drawTex((0.2, 0.8, 'Scaling: %.2f' % self.scaleFactor))]
    return []

  #
  # Save the histogram to a results.cache file, useful when you need to do further operations on it later
  #
  def saveToCache(self, dir, sys):
    try:    os.makedirs(os.path.join(dir))
    except: pass

    resultFile = os.path.join(dir, self.name + '.pkl')
    histos     = {s.name+s.texName: h for s, h in self.histos.iteritems()}
    plotName   = self.name+(sys if sys else '')
    try:
      with lock(resultFile, 'rb', keepLock=True) as f: allPlots = pickle.load(f)
      allPlots.update({plotName : histos})
    except:
      allPlots = {plotName : histos}
    with lock(resultFile, 'wb', existingLock=True) as f: pickle.dump(allPlots, f)
    log.info("Plot " + plotName + " saved to cache")


  #
  # Load from cache
  #
  def loadFromCache(self, resultsDir):
    resultsFile = os.path.join(resultsDir, self.name + '.pkl')
    try:
      with lock(resultsFile, 'rb') as f: allPlots = pickle.load(f)
      for s in self.histos.keys():
        self.histos[s] = allPlots[self.name][s.name+s.texName]
    except:
      log.warning('No resultsfile for ' + self.name + '.pkl')
      return True

  #
  # Get Yields
  #
  def getYields(self, bin=None):
    if bin: return {s.name : h.GetBinContent(bin) for s,h in self.histos.iteritems()}
    else:   return {s.name : h.Integral()         for s,h in self.histos.iteritems()}


  #
  # Make a correct ratio graph (also working for poisson errors, and showing error bars for points outside of y-axis range)
  #
  def makeRatioGraph(self, num, den):
    graph = ROOT.TGraphAsymmErrors(num)
    graph.Set(0)
    for bin in range(1, num.GetNbinsX()+1):
      if den.GetBinContent(bin) > 0:
        center  = num.GetBinCenter(bin)
        val     = num.GetBinContent(bin)/den.GetBinContent(bin)
        errUp   = num.GetBinErrorUp(bin)/den.GetBinContent(bin)  if val > 0 else 0
        errDown = num.GetBinErrorLow(bin)/den.GetBinContent(bin) if val > 0 else 0
        graph.SetPoint(bin, center, val)
        graph.SetPointError(bin, 0, 0, errDown, errUp)
    return graph



  #
  # Get ratio line
  #
  def getRatioLine(self, min, max):
    line = ROOT.TPolyLine(2)
    line.SetPoint(0, self.xmin, 1.)
    line.SetPoint(1, self.xmax, 1.)
    line.SetLineWidth(1)
    return line

  #
  # Get legend
  #
  def getLegend(self, columns, coordinates, histos):
    legend = ROOT.TLegend(*coordinates)
    legend.SetNColumns(columns)
    legend.SetFillStyle(0)
    legend.SetShadowColor(ROOT.kWhite)
    legend.SetBorderSize(0)
    for h in sum(histos, []): legend.AddEntry(h, h.texName, h.legendStyle)
    return legend


  #
  # Applying post-fit values
  #
  def applyPostFitScaling(self, postFitInfo):
    for sample, h in self.histos.iteritems():
      for key,value in postFitInfo.iteritems():
        if key in sample.name or key in sample.texName:
          log.debug('Applying post-fit scaling value of ' + str(value) + ' to ' + sample.name)
          h.Scale(value)


  #
  # Adding systematics to MC (assuming MC is first in the stack list)
  #
  def calcSystematics(self, systematics, linearSystematics, resultsDir, postFitInfo=None):
    resultsFile = os.path.join(resultsDir, self.name + '.pkl')
    with lock(resultsFile, 'rb') as f: allPlots = pickle.load(f)

    def sumHistos(list):
      sum = list[0].Clone()
      for h in list[1:]: sum.Add(h)
      return sum

    histNames = [s.name+s.texName for s in self.stack[0]]

    histos_summed = {}
    for sys in systematics.keys() + [None]:
      plotName = self.name+(sys if sys else '')
      if plotName not in allPlots.keys():
        if 'sideBand' in sys: allPlots[plotName] = {}
        else:                 log.error('No ' + sys + ' variation found for ' +  self.name)
      for histName in histNames:
        if sys and 'Scale' in sys: # Ugly hack to apply scale systematics on MC instead of data
          data, dataSys = None, None
          for dataset in ['MuonEG','DoubleEG','DoubleMuon']:
            if (dataset + 'data') not in allPlots[self.name]: continue
            data    = addHist(data,    allPlots[self.name][dataset+'data'])
            dataSys = addHist(dataSys, allPlots[self.name+sys][dataset+'data'])
          if data: allPlots[plotName][histName] = applySysToOtherHist(data, dataSys, allPlots[plotName][histName])
        if sys and 'sideBand' in sys: # Ugly hack to apply side band uncertainty
          allPlots[plotName][histName] = applySidebandUnc(allPlots[self.name][histName], self.name, resultsDir, 'Up' in sys)
        h = allPlots[plotName][histName]
        if postFitInfo:
          for i in postFitInfo:
            if histName.count(i): h.Scale(postFitInfo[i])
        if h.Integral()==0: log.debug("Found empty histogram %s:%s in %s/%s.pkl", plotName, histName, resultsDir, self.name)
        if self.scaleFactor: h.Scale(self.scaleFactor)
        normalizeBinWidth(h, self.normBinWidth)
        self.addOverFlowBin1D(h, self.overflowBin)


      histos_summed[sys] = sumHistos([allPlots[plotName][histName] for histName in histNames])

    sysList = [sys.replace('Up','') for sys in systematics if sys.count('Up')]

    h_sys = {}
    for sys in sysList:
      h_sys[sys] = histos_summed[sys+'Up'].Clone()
      h_sys[sys].Scale(-1)
      h_sys[sys].Add(histos_summed[sys+'Down'])

    h_rel_err = histos_summed[None].Clone()
    h_rel_err.Reset()

    # Adding the systematics in quadrature
    for k in h_sys.keys():
      for ib in range(h_rel_err.GetNbinsX()+1):
        h_rel_err.SetBinContent(ib, h_rel_err.GetBinContent(ib) + (h_sys[k].GetBinContent(ib)/2)**2 )

    for sampleFilter, unc in linearSystematics.values():
      for ib in range(h_rel_err.GetNbinsX()+1):
        if sampleFilter: uncertainty = unc/100*sum([h.GetBinContent(ib) for s,h in self.histos.iteritems() if any([s.name.count(f) for f in sampleFilter])])
        else:            uncertainty = unc/100*sum([h.GetBinContent(ib) for s,h in self.histos.iteritems()])
        h_rel_err.SetBinContent(ib, h_rel_err.GetBinContent(ib) + uncertainty**2)

    for ib in range(h_rel_err.GetNbinsX()+1):
      h_rel_err.SetBinContent(ib, sqrt(h_rel_err.GetBinContent(ib)))

    # Divide by the summed hist to get relative errors, and return
    h_rel_err.Divide(histos_summed[None])
    return h_rel_err

  def getSystematicBand(self, totalMC, sysValues):
    boxes, ratio_boxes = [], []
    for ib in range(1, 1 + totalMC.GetNbinsX()):
      val = totalMC.GetBinContent(i)
      if val > 0:
        sys   = sysValues.GetBinContent(i)
        box   = ROOT.TBox(totalMC.GetXaxis().GetBinLowEdge(ib),  max([0.003, (1-sys)*val]), totalMC.GetXaxis().GetBinUpEdge(ib), max([0.003, (1+sys)*val]))
        r_box = ROOT.TBox(totalMC.GetXaxis().GetBinLowEdge(ib),  max(0.1, 1-sys),           totalMC.GetXaxis().GetBinUpEdge(ib), min(1.9, 1+sys))
        for b in [box, r_box]:
          b.SetLineColor(ROOT.kBlack)
          b.SetFillStyle(3444)
          b.SetFillColor(ROOT.kBlack)
        boxes.append(box)
        ratio_boxes.append(r_box)
    return boxes, ratio_boxes

  #
  # Get filled bins in plot
  #
  def getFilledBins(self, histos, threshold=0):
    filledBins = []
    for bin in range(1, histos[0][0].GetNbinsX()+1):
      if any([h[0].GetBinContent(bin) > threshold for h in histos]): filledBins.append(bin)
    return filledBins

  #
  # Remove empty bins from plot
  #
  def removeEmptyBins(self, histos, threshold):
    filledBins = self.getFilledBins(histos, threshold)
    self.xmin   = histos[0][0].GetBinLowEdge(filledBins[0])
    self.xmax   = histos[0][0].GetBinLowEdge(filledBins[-1]+1)
    for h in histos:
      h[0].GetXaxis().SetRangeUser(self.xmin, self.xmax)

  #
  # Draw function
  #
  def draw(self, \
          yRange = "auto",
          extensions = ["pdf", "png", "root","C"],
          plot_directory = ".",
          logX = False, logY = True,
          ratio = None,
          scaling = {},
          sorting = False,
          legend = "auto",
          drawObjects = [],
          widths = {},
          canvasModifications = [],
          histModifications = [],
          ratioModifications = [],
          systematics = {},
          linearSystematics = {},
          resultsDir = None,
          postFitInfo = None,
          saveGitInfo = True,
          ):
    ''' yRange: 'auto' (default) or [low, high] where low/high can be 'auto'
        extensions: ["pdf", "png", "root"] (default)
        logX: True/False (default), logY: True(default)/False
        ratio: 'auto'(default) corresponds to {'num':1, 'den':0, 'logY':False, 'style':None, 'texY': 'Data / MC', 'yRange': (0.5, 1.5), 'drawObjects': []}
        scaling: {} (default). Scaling the i-th stack to the j-th is done by scaling = {i:j} with i,j integers
        sorting: True/False(default) Whether or not to sort the components of a stack wrt Integral
        legend: "auto" (default) or [x_low, y_low, x_high, y_high] or None. ([<legend_coordinates>], n) divides the legend into n columns.
        drawObjects = [] Additional ROOT objects that are called by .Draw()
        widths = {} (default) to update the widths. Values are {'y_width':500, 'x_width':500, 'y_ratio_width':200}
        canvasModifications = [] could be used to pass on lambdas to modify the canvas
    '''

    # Canvas widths
    default_widths = {'y_width':500, 'x_width': 520, 'y_ratio_width': (200 if ratio else None)}
    default_widths.update(widths)

    # Make sure ratio dict has all the keys by updating the default
    if ratio:
      defaultRatioStyle = {'num':1, 'den':0, 'logY':False, 'style':None, 'texY': 'obs./exp.', 'yRange': (0.5, 1.5), 'drawObjects':[]}
      if type(ratio)!=type({}): raise ValueError( "'ratio' must be dict (default: {}). General form is '%r'." % defaultRatioStyle)
      defaultRatioStyle.update(ratio)
      ratio = defaultRatioStyle

    # If a results directory is given, we can load the histograms from former runs
    if resultsDir:
      err = self.loadFromCache(resultsDir)
      if err: return True

    if postFitInfo: self.applyPostFitScaling(postFitInfo)

    histDict = {i: h.Clone() for i, h in self.histos.iteritems()}

    # Check if at least one entry is present
    if not sum([h.Integral() for h in self.histos.values()]) > 0:
      log.info('Empty histograms for ' + self.name + ', skipping')
      return

    # Apply style to histograms + normalize bin width + add overflow bin
    for s, h in histDict.iteritems():
      if hasattr(s, 'style'): s.style(h)
      h.texName = s.texName
      normalizeBinWidth(h, self.normBinWidth)
      self.addOverFlowBin1D(h, self.overflowBin)

    # Transform histDict --> histos where the stacks are added up
    # Note self.stack is of form [[A1, A2, A3,...],[B1,B2,...],...] where the sublists need to be stacked
    histos = []
    for stack in self.stack:
      histsToStack = [histDict[s] for s in stack]
      histos.append(self.stackHists(histsToStack))

    drawObjects += self.scaleStacks(histos, scaling)

    # Check if at least two bins are filled, otherwise skip, unless yield
    if len(self.getFilledBins(histos)) < 2 and self.name != 'yield':
      log.info('Seems all events end up in the same bin for ' + self.name + ', will not produce output for this uninteresting plot')
      return

    # Calculate the systematics on the first stack
    if len(systematics) or len(linearSystematics):
      sysValues = self.calcSystematics(systematics, linearSystematics, resultsDir, postFitInfo)

    # Get the canvas, which includes canvas.topPad and canvas.bottomPad
    canvas = getDefaultCanvas(default_widths['x_width'], default_widths['y_width'], default_widths['y_ratio_width'])
    for modification in canvasModifications: modification(canvas)

    canvas.topPad.cd()

    # Range on y axis and remove empty bins
    max_ = max(l[0].GetMaximum() for l in histos)
    min_ = min(l[0].GetMinimum() for l in histos)

    if type(yRange)==type(()) and len(yRange)==2:
      yMin_ = yRange[0] if not yRange[0]=="auto" else (0.7          if logY else (0 if min_>0 else 1.2*min_))
      yMax_ = yRange[1] if not yRange[1]=="auto" else (10**0.5*max_ if logY else 1.2*max_)

    self.removeEmptyBins(histos, yMin_ if logY or min_ < 0 else yMax_/200.)

    # If legend is in the form (tuple, int) then the number of columns is provided
    if len(legend) == 2: legendColumns, legend = legend[1], legend[0]
    else:                legendColumns, legend = 1, legend

    #Calculate legend coordinates in gPad coordinates
    if legend:
      if legend=="auto": legendCoordinates = (0.50,0.9-0.05*sum(map(len, histos)),0.92,0.9)
      else:              legendCoordinates = legend

      #Avoid overlap with the legend
      if (yRange=="auto" or yRange[1]=="auto"):
        scaleFactor = 1
        from ttg.tools.style import fromAxisToNDC, fromNDCToAxis
        for histo in [h[0] for h in histos]:
          for i in range(1, 1 + histo.GetNbinsX()):
            xLowerEdge  = fromAxisToNDC(canvas.topPad, histo.GetXaxis(), histo.GetBinLowEdge(i))
            xUpperEdge  = fromAxisToNDC(canvas.topPad, histo.GetXaxis(), histo.GetBinLowEdge(i)+histo.GetBinWidth(i))

            # maximum allowed fraction in bin to avoid overlap with legend
            if xUpperEdge > legendCoordinates[0] and xLowerEdge < legendCoordinates[2]: maxFraction = 0.96*max(0.3, fromNDCToAxis(canvas.topPad, histo.GetYaxis(), legendCoordinates[3], isY=True))
            else:                                                                       maxFraction = 0.96

            # Use: (y - yMin_) / (sf*yMax_ - yMin_) = maxFraction (and y->log(y) in log case).
            # Compute the maximum required scale factor s.
            y = histo.GetBinContent(i)+max(sysValues[i] if len(systematics) or len(linearSystematics) else 0, histo.GetBinError(i))
            try:
              if logY: scaleFactor = max(scaleFactor, yMin_/yMax_*(y/yMin_)**(1./maxFraction) if y>0 else 1)
              else:    scaleFactor = max(scaleFactor, 1./yMax_*(yMin_ + (y-yMin_)/maxFraction))
              scaleFactor = new_sf if new_sf>scaleFactor else scaleFactor
            except ZeroDivisionError:
              pass

        yMax_ = scaleFactor*yMax_

    # Draw the histos
    same = ""
    for h in sum(histos, []):
      drawOption = h.drawOption if hasattr(h, "drawOption") else "hist"
      canvas.topPad.SetLogy(logY)
      canvas.topPad.SetLogx(logX)
      h.GetYaxis().SetRangeUser(yMin_, yMax_)
      h.GetXaxis().SetTitle(self.texX)
      h.GetYaxis().SetTitle(self.texY)

      if ratio is None: h.GetYaxis().SetTitleOffset(1.3)
      else:             h.GetYaxis().SetTitleOffset(1.6)

      for modification in histModifications+self.histModifications: modification(h)

      h.Draw(drawOption+same)
      same = "same"

    canvas.topPad.RedrawAxis()

    if len(systematics) or len(linearSystematics):
      boxes, ratioBoxes                = self.getSystematicBand(histos[0][0], sysValues)
      drawObjects                     += boxes
      if ratio: ratio['drawObjects']  += ratioBoxes

    if legend: drawObjects += [self.getLegend(legendColumns, legendCoordinates, histos)]
    for o in drawObjects:
      try:    o.Draw()
      except: log.debug( "drawObjects has something I can't Draw(): %r", o)

    # Make a ratio plot
    if ratio:
      canvas.bottomPad.cd()
      num = histos[ratio['num']][0]
      den = histos[ratio['den']][0]

      h_ratio = num.Clone()
      h_ratio.Divide(den)

      if ratio['style']: ratio['style'](h_ratio)

      h_ratio.GetXaxis().SetTitle(self.texX)
      h_ratio.GetYaxis().SetTitle(ratio['texY'])

      h_ratio.GetXaxis().SetTitleOffset( 3.2 )
      h_ratio.GetYaxis().SetTitleOffset( 1.6 )

      h_ratio.GetXaxis().SetTickLength( 0.03*3 )
      h_ratio.GetYaxis().SetTickLength( 0.03*2 )

      h_ratio.GetYaxis().SetRangeUser( *ratio['yRange'] )
      h_ratio.GetYaxis().SetNdivisions(505)

      for modification in ratioModifications: modification(h_ratio)

      if num.drawOption == "e1":
        for bin in range(1, h_ratio.GetNbinsX()+1): h_ratio.SetBinError(bin, 0.0001)     # do not show error bars on hist, those are taken overf by the TGraphAsymmErrors
        h_ratio.Draw("e0")
        graph = self.makeRatioGraph(num, den)
        if den.drawOption == "e1":                                                       # show error bars from denominator
          graph2 = self.makeRatioGraph(den, den)
          graph2.Draw("0 same")
        graph.Draw("P0 same")
      else:
        h_ratio.Draw(num.drawOption)

      canvas.bottomPad.SetLogx(logX)
      canvas.bottomPad.SetLogy(ratio['logY'])

      ratio['drawObjects'] += [self.getRatioLine(h_ratio.GetXaxis().GetXmin(), h_ratio.GetXaxis().GetXmax())]
      for o in ratio['drawObjects']:
        try:    o.Draw()
        except: log.debug( "ratio['drawObjects'] has something I can't Draw(): %r", o)

    try:    os.makedirs(plot_directory)
    except: pass
    copyIndexPHP(plot_directory)

    canvas.cd()

    if saveGitInfo: copyGitInfo(os.path.join(plot_directory, self.name + '.gitInfo'))
    log.info('Creating output files for ' + self.name)
    for extension in extensions:
      ofile = os.path.join(plot_directory, "%s.%s"%(self.name, extension))
      canvas.Print(ofile)
