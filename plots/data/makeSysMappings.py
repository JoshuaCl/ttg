#! /usr/bin/env python

with open('sysMappingsTemplate.json', 'r') as template:
  with open('sysMappings.json', 'w') as mapping:
    for line in template:
      if line.count('STATERRORS'):
        for photonTypeShort, photonType in [('h', 'hadronic photon'), ('g', 'genuine photon'), ('f', 'hadronic fake')]:
          for i in range(1,8):
            mapping.write('  "chgIsoall_' + photonTypeShort + 'Stat' + str(i) + '" : "Stats ' + photonType + ' bin ' + str(i) + '",\n')
        for sample, sampleTex in [('TTGamma', 't#bar{t}#gamma'), ('TTJets', 't#bar{t}'), ('ZG', 'Z#gamma'), ('DY', 'Drell-Yan'), ('other', 'Other')]:
          for signs in ['SF', 'OF']:
            for bin, mult in [('1', '1j,1b'), ('2', '#geq2j,0b'), ('3', '#geq2j,1b'), ('4', '#geq2j,#geq2b')]:
              mapping.write('  "sr_' + signs + sample + 'Stat' + bin + '" : "Stats ' + sampleTex + ' ' + mult + ' (' + signs + ')",\n')
              mapping.write('  "zg_' + signs + sample + 'Stat' + bin + '" : "Stats ' + sampleTex + ' ' + mult + ' (Z#gamma ' + signs + ')",\n')
        for bin, mult in [('0', '1j,1b'), ('1', '#geq2j,0b'), ('2', '#geq2j,1b'), ('3', '#geq2j,#geq2b')]:   # AutoMCStats, bin numbering starts at 0!
            mapping.write('  "prop_binsr_SF_bin' + bin + '" : "Stats ' + mult + ' (SF SR)",\n')
            mapping.write('  "prop_binsr_OF_bin' + bin + '" : "Stats ' + mult + ' (OF SR)",\n')
            mapping.write('  "prop_binzg_SF_bin' + bin + '" : "Stats ' + mult + ' (Z#gamma CR)",\n')
        for i in range(7):
          mapping.write('  "prop_binchgIso_bin' + str(i) + '" : "Stats bin ' + str(i) + '",\n')
      else:
        mapping.write(line)
