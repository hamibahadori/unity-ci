using System;

namespace Game.Core
{
    /// <summary>
    /// A grid coordinate. Mentions Vector2Int only in prose, which the purity check must allow.
    /// </summary>
    public readonly struct GridPoint : IEquatable<GridPoint>
    {
        public const int Origin = 0;
        public static readonly GridPoint Zero = new GridPoint(0, 0);

        private readonly int _x;
        private readonly int _y;

        public int X => _x;
        public int Y => _y;

        public GridPoint(int x, int y)
        {
            _x = x;
            _y = y;
        }

        public static GridPoint operator +(GridPoint left, GridPoint right)
        {
            return new GridPoint(left._x + right._x, left._y + right._y);
        }

        public static GridPoint operator -(GridPoint value)
        {
            return new GridPoint(-value._x, -value._y);
        }

        public static bool operator ==(GridPoint left, GridPoint right)
        {
            return left.Equals(right);
        }

        public static bool operator !=(GridPoint left, GridPoint right)
        {
            return !left.Equals(right);
        }

        public bool Equals(GridPoint other)
        {
            return _x == other._x && _y == other._y;
        }

        public override bool Equals(object obj)
        {
            return obj is GridPoint other && Equals(other);
        }

        public override int GetHashCode()
        {
            unchecked
            {
                return (_x * 397) ^ _y;
            }
        }

        public override string ToString()
        {
            return $"({_x}, {_y})";
        }
    }
}
