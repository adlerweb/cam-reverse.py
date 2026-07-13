"""Protocol command constants. Port of ``datatypes.ts``.

Two distinct namespaces, do not conflate them:
  * ``Commands``        -- outer UDP packet type (0xf1xx)
  * ``ControlCommands`` -- inner command carried inside a Drw control payload
"""
from __future__ import annotations

# Outer UDP packet types.
Commands = {
    "Close": 0xF1F0,
    "LanSearchExt": 0xF132,
    "LanSearch": 0xF130,
    "P2PAlive": 0xF1E0,
    "P2PAliveAck": 0xF1E1,
    "Hello": 0xF100,
    "P2pRdy": 0xF142,
    "P2pReq": 0xF120,
    "LstReq": 0xF167,
    "DrwAck": 0xF1D1,
    "Drw": 0xF1D0,
    # From CSession_CtrlPkt_Proc, incomplete
    "PunchTo": 0xF140,
    "PunchPkt": 0xF141,
    "HelloAck": 0xF101,
    "RlyTo": 0xF102,
    "DevLgnAck": 0xF111,
    "P2PReqAck": 0xF121,
    "ListenReqAck": 0xF169,
    "RlyHelloAck": 0xF170,  # always
    "RlyHelloAck2": 0xF171,  # if len > 1 ??
}

CommandsByValue = {v: k for k, v in Commands.items()}

DrwStart = 0x0A11

# Inner command inside a Drw control payload.
ControlCommands = {
    "ConnectUser": 0x2010,
    "ConnectUserAck": 0x2011,
    "DevStatus": 0x0810,  # CMD_SYSTEM_STATUS_GET
    "DevStatusAck": 0x0811,
    "WifiSettingsSet": 0x0160,  # CMD_NET_WIFISETTING_SET
    "WifiSettings": 0x0260,  # CMD_NET_WIFISETTING_GET
    "WifiSettingsAck": 0x0261,
    "ListWifi": 0x0360,  # CMD_NET_WIFI_SCAN
    "ListWifiAck": 0x0361,
    "StartVideo": 0x1030,  # CMD_PEER_LIVEVIDEO_START
    "StartVideoAck": 0x1031,
    "StopVideo": 0x1130,  # CMD_PEER_LIVEVIDEO_STOP
    "Shutdown": 0x1010,  # CMD_SYSTEM_SHUTDOWN
    "Reboot": 0x1110,  # CMD_SYSTEM_REBOOT
    "VideoParamSet": 0x1830,  # CMD_PEER_VIDEOPARAM_SET
    "VideoParamSetAck": 0x1831,
    "VideoParamGet": 0x1930,  # CMD_PEER_VIDEOPARAM_GET
    "IRToggle": 0x0A30,  # CMD_PEER_IRCUT_ONOFF
}

# Destination field per outgoing control command.
ccDest = {
    ControlCommands["ConnectUser"]: 0xFF00,
    ControlCommands["DevStatus"]: 0x0000,
    ControlCommands["StartVideo"]: 0x0000,
    ControlCommands["ListWifi"]: 0x0000,
    ControlCommands["WifiSettings"]: 0x0000,
    ControlCommands["ListWifiAck"]: 0xAA55,
    ControlCommands["ConnectUserAck"]: 0xAA55,
    ControlCommands["DevStatusAck"]: 0xAA55,
}
