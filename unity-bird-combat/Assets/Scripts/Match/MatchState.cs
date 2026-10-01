using UnityEngine;

namespace BirdCombat.Match
{
    public enum MatchPhase
    {
        Lobby = 0,
        Countdown = 1,
        Active = 2,
        SuddenDeath = 3,
        Completed = 4
    }

    public enum VictoryCondition
    {
        EggCapture,
        TeamWipe,
        Timeout
    }
}
