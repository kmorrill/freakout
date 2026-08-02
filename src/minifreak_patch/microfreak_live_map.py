"""Hardware-correlated MicroFreak structured-field to live-word map.

Generated from a diversity-optimized 40-preset corpus on firmware 5.0.0.36,
then extended by collision-resistant saved-preset sentinels for four formerly
constant fields and three formerly confounded chord offsets. Every published
address has hardware readback and exact restoration. Unresolved constants are
kept explicit instead of being guessed.
"""

from __future__ import annotations

MICROFREAK_STRUCTURED_LIVE_WORDS: dict[str, tuple[int, ...]] = {
    'Arp.Dice': (0x030F, 0x0407,),  # saved sentinel hardware proof
    'Arp.Dir': (0x0408,),  # 4 distinct saved values
    'Arp.Div': (0x030A, 0x0402),  # 4 distinct saved values
    'Arp.Enable': (0x020F, 0x0308, 0x0400),  # 2 distinct saved values
    'Arp.Range': (0x0309, 0x0401),  # 4 distinct saved values
    'Arp.Rate': (0x030B, 0x0403),  # 19 distinct saved values
    'Arp.SeqOn': (0x0409,),  # 2 distinct saved values
    'Arp.Spice': (0x030E, 0x0406),  # 4 distinct saved values
    'Arp.Swing': (0x030C, 0x0404),  # 5 distinct saved values
    'Arp.Sync': (0x030D, 0x0405),  # 2 distinct saved values
    'Co1.EG1': (0x060D, 0x0906, 0x0A00),  # 13 distinct saved values
    'Co1.EG2': (0x060E, 0x0907, 0x0A01),  # 7 distinct saved values
    'Co1.Key': (0x090A, 0x0A04),  # 6 distinct saved values
    'Co1.LFO': (0x060F, 0x0908, 0x0A02),  # 9 distinct saved values
    'Co1.Xpr': (0x0909, 0x0A03),  # 4 distinct saved values
    'Co2.EG1': (0x090C, 0x0A06, 0x0B00),  # 17 distinct saved values
    'Co2.EG2': (0x090D, 0x0A07, 0x0B01),  # 8 distinct saved values
    'Co2.Key': (0x0A0A, 0x0B04),  # 3 distinct saved values
    'Co2.LFO': (0x090E, 0x0A08, 0x0B02),  # 9 distinct saved values
    'Co2.Xpr': (0x090F, 0x0A09, 0x0B03),  # 8 distinct saved values
    'Co3.EG1': (0x0A0C, 0x0B06, 0x0C00),  # 12 distinct saved values
    'Co3.EG2': (0x0A0D, 0x0B07, 0x0C01),  # 10 distinct saved values
    'Co3.Key': (0x0B0A, 0x0C04),  # 5 distinct saved values
    'Co3.LFO': (0x0A0E, 0x0B08, 0x0C02),  # 19 distinct saved values
    'Co3.Xpr': (0x0A0F, 0x0B09, 0x0C03),  # 11 distinct saved values
    'Co4.EG1': (0x0B0C, 0x0C06, 0x0D00),  # 12 distinct saved values
    'Co4.EG2': (0x0B0D, 0x0C07, 0x0D01),  # 36 distinct saved values
    'Co4.Key': (0x0C0A, 0x0D04),  # 12 distinct saved values
    'Co4.LFO': (0x0B0E, 0x0C08, 0x0D02),  # 13 distinct saved values
    'Co4.Xpr': (0x0B0F, 0x0C09, 0x0D03),  # 16 distinct saved values
    'Co5.EG1': (0x0C0C, 0x0D06, 0x0E00),  # 12 distinct saved values
    'Co5.EG2': (0x0C0D, 0x0D07, 0x0E01),  # 8 distinct saved values
    'Co5.Key': (0x0D0A, 0x0E04),  # 5 distinct saved values
    'Co5.LFO': (0x0C0E, 0x0D08, 0x0E02),  # 16 distinct saved values
    'Co5.Xpr': (0x0C0F, 0x0D09, 0x0E03),  # 8 distinct saved values
    'Co6.EG1': (0x0D0C, 0x0E06, 0x0F00),  # 9 distinct saved values
    'Co6.EG2': (0x0D0D, 0x0E07, 0x0F01),  # 8 distinct saved values
    'Co6.Key': (0x0E0A, 0x0F04),  # 7 distinct saved values
    'Co6.LFO': (0x0D0E, 0x0E08, 0x0F02),  # 14 distinct saved values
    'Co6.Xpr': (0x0D0F, 0x0E09, 0x0F03),  # 9 distinct saved values
    'Co7.EG1': (0x0E0C, 0x0F06, 0x1000),  # 10 distinct saved values
    'Co7.EG2': (0x0E0D, 0x0F07, 0x1001),  # 8 distinct saved values
    'Co7.Key': (0x0F0A, 0x1004),  # 5 distinct saved values
    'Co7.LFO': (0x0E0E, 0x0F08, 0x1002),  # 10 distinct saved values
    'Co7.Xpr': (0x0E0F, 0x0F09, 0x1003),  # 8 distinct saved values
    'EG1.Amount': (0x0109, 0x0206),  # 23 distinct saved values
    'EG1.FallLvl': (0x0106, 0x0203, 0x100D),  # 33 distinct saved values
    'EG1.FallSlp': (0x0108, 0x0205, 0x100F),  # 12 distinct saved values
    'EG1.Hold': (0x0107, 0x0204, 0x100E),  # 11 distinct saved values
    'EG1.Mode': (0x0103, 0x0200, 0x100A),  # 3 distinct saved values
    'EG1.RiseLvl': (0x0104, 0x0201, 0x100B),  # 19 distinct saved values
    'EG1.RiseSlp': (0x0105, 0x0202, 0x100C),  # 9 distinct saved values
    'EG2.Attack': (0x000B, 0x0601),  # 14 distinct saved values
    'EG2.DecRel': (0x000C, 0x0602),  # 40 distinct saved values
    'EG2.Legato': (0x000E, 0x0604),  # 2 distinct saved values
    'EG2.Mode': (0x000A, 0x0600),  # 2 distinct saved values
    'EG2.Sustain': (0x000D, 0x0603),  # 25 distinct saved values
    'Gen.Chord': (0x050C, 0x0707),  # 2 distinct saved values
    'Gen.ChOffs1': (0x050D, 0x0708),  # raw saved sentinel hardware proof
    'Gen.ChOffs2': (0x050E, 0x0709),  # raw saved sentinel hardware proof
    'Gen.ChOffs3': (0x050F, 0x070A),  # raw saved sentinel hardware proof
    'Gen.Parafon': (0x040F, 0x0505, 0x0700),  # 2 distinct saved values
    'Gen.PolyCnt': (0x0507, 0x0702),  # 2 distinct saved values
    'Gen.PrstVol': (0x0508, 0x0703),  # 13 distinct saved values
    'Gen.UniCnt': (0x050B, 0x0706),  # 3 distinct saved values
    'Gen.UniSprd': (0x050A, 0x0705),  # 8 distinct saved values
    'Gen.Volume': (0x0509, 0x0704),  # 2 distinct saved values
    'Kbd.GlMode': (0x010E, 0x020B, 0x0304),  # 4 distinct saved values
    'Kbd.Glide': (0x010A, 0x0207, 0x0300),  # 9 distinct saved values
    'Kbd.Hold': (0x010D, 0x020A, 0x0303),  # saved sentinel hardware proof
    'Kbd.Octave': (0x010B, 0x0208, 0x0301),  # 6 distinct saved values
    'Kbd.PresAmp': (0x010F, 0x020C, 0x0305),  # 6 distinct saved values
    'Kbd.Root': (0x020E, 0x0307),  # saved sentinel hardware proof
    'Kbd.Scale': (0x020D, 0x0306),  # 3 distinct saved values
    'Kbd.Veloc': (0x010C, 0x0209, 0x0302),  # 2 distinct saved values
    'LFO.Div': (0x040B, 0x0501),  # 13 distinct saved values
    'LFO.Rate': (0x040C, 0x0502),  # 26 distinct saved values
    'LFO.Retrig': (0x040E, 0x0504),  # 3 distinct saved values
    'LFO.Shape': (0x040A, 0x0500),  # 6 distinct saved values
    'LFO.Sync': (0x040D, 0x0503),  # 2 distinct saved values
    'Mat.Assign1': (0x0609, 0x0902),  # 14 distinct saved values
    'Mat.Assign2': (0x060A, 0x0903),  # 14 distinct saved values
    'Mat.Assign3': (0x060B, 0x0904),  # 12 distinct saved values
    'Seq.GateLen': (0x070E, 0x1202),  # 7 distinct saved values
    'Seq.XiceRst': (0x070D, 0x1201),  # saved sentinel hardware proof
    'Seq.Length': (0x070C, 0x1200),  # 8 distinct saved values
    'Seq.Smooth1': (0x070F, 0x1203),  # 2 distinct saved values
    'Seq.Smooth2': (0x1204,),  # 2 distinct saved values
    'Seq.Smooth3': (0x1205,),  # 2 distinct saved values
    'Seq.Smooth4': (0x1206,),  # 2 distinct saved values
    'VCF.Cutoff': (0x0101, 0x0F0E, 0x1008),  # 37 distinct saved values
    'VCF.Reso': (0x0102, 0x0F0F, 0x1009),  # 33 distinct saved values
    'VCF.Type': (0x0100, 0x0F0D, 0x1007),  # 3 distinct saved values
    'VCO.BendRng': (0x0007,),  # 6 distinct saved values
    'VCO.Param1': (0x0001,),  # 28 distinct saved values
    'VCO.Param2': (0x0003,),  # 32 distinct saved values
    'VCO.Param3': (0x0005,),  # 31 distinct saved values
    'Voc.HissMod': (0x1207, 0x1300),  # 3 distinct saved values
    'Voc.HissVol': (0x1208, 0x1301),  # 2 distinct saved values
}

MICROFREAK_STRUCTURED_LIVE_AMBIGUOUS = ()
MICROFREAK_STRUCTURED_CORPUS_NONVARYING = ('Arp.Dice', 'Gen.Panel', 'Kbd.Hold', 'Kbd.Root', 'Mat.MatBtn', 'Mat.MatEnc', 'Seq.XiceRst', 'Sys.PrsetBt', 'Sys.PrsetID', 'Sys.Save', 'Sys.Utility')
MICROFREAK_STRUCTURED_CORPUS_NONVARYING_UNRESOLVED = ('Gen.Panel', 'Mat.MatBtn', 'Mat.MatEnc', 'Sys.PrsetBt', 'Sys.PrsetID', 'Sys.Save', 'Sys.Utility')
MICROFREAK_STRUCTURED_NO_LIVE_TABLE_CC_EFFECT = ('Kbd.Hold',)
MICROFREAK_STRUCTURED_GLOBAL_COUNTERPARTS = {'Kbd.Root': 'keyboard.root_note'}
MICROFREAK_STRUCTURED_LIVE_EVIDENCE = 'hardware_saved_live_diverse_40_exact_restore'
MICROFREAK_STRUCTURED_LIVE_FIELD_EVIDENCE = {
    'Arp.Dice': 'hardware_saved_bulk_sentinel_plus_operation49_exact_restore',
    'Gen.ChOffs1': 'hardware_saved_raw_bulk_sentinel_plus_operation49_exact_restore',
    'Gen.ChOffs2': 'hardware_saved_raw_bulk_sentinel_plus_operation49_exact_restore',
    'Gen.ChOffs3': 'hardware_saved_raw_bulk_sentinel_plus_operation49_exact_restore',
    'Mat.Assign1': 'hardware_saved_live_corpus_plus_destination_id_operation49_exact_restore',
    'Mat.Assign2': 'hardware_saved_live_corpus_plus_destination_id_operation49_exact_restore',
    'Mat.Assign3': 'hardware_saved_live_corpus_plus_destination_id_operation49_exact_restore',
    'Kbd.Hold': 'hardware_saved_bulk_sentinel_plus_operation49_exact_restore',
    'Kbd.Root': 'hardware_saved_bulk_sentinel_plus_operation49_exact_restore',
    'Seq.XiceRst': 'hardware_saved_bulk_sentinel_plus_operation49_exact_restore',
}
