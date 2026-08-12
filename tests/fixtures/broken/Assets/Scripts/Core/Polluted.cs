using UnityEngine;

namespace Game.Core
{
    /// <summary>Engine reference inside an assembly declaring noEngineReferences.</summary>
    public class Polluted
    {
        private readonly Vector2Int _cell = Vector2Int.zero;

        public int SumOfComponents()
        {
            return _cell.x + _cell.y;
        }
    }
}
