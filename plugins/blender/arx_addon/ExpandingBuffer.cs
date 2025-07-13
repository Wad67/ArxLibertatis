using ArxLibertatisEditorIO.MediumIO.Shared;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;
using System.Security.Cryptography;
using System.Text;

namespace ArxLibertatisEditorIO.RawIO.PK.Implode
{
    public class ExpandingBuffer
    {
        const int blockSize = 0x1000;

        byte[] heap;
        int startIndex = 0, startIndexBackup = 0;
        int endIndex = 0, endIndexBackup = 0;

        public ExpandingBuffer(int numberOfBytes = 0)
        {
            heap = new byte[numberOfBytes];
        }

        ReadOnlySpan<byte> getActualDataAsSpan(int offset = 0)
        {
            var start = startIndex + offset;
            return heap.AsSpan(start, endIndex - start);
        }

        ReadOnlyMemory<byte> getActualDataAsMemory(int offset = 0)
        {
            var start = startIndex + offset;
            return heap.AsMemory(start, endIndex - start);
        }

        /// <summary>
        /// Returns the number of bytes in the stored data.
        /// </summary>
        /// <returns></returns>
        public int size()
        {
            return endIndex - startIndex;
        }

        public bool isEmpty()
        {
            return size() == 0;
        }

        /// <summary>
        /// Returns the underlying Buffer's (heap) size.
        /// </summary>
        /// <returns></returns>
        public int heapSize()
        {
            return heap.Length;
        }

        /// <summary>
        /// Sets a single byte of the stored data
        /// If offset is negative, then the method calculates the index from the end backwards
        /// </summary>
        /// <param name="offset"></param>
        /// <param name="value"></param>
        public void setByte(int offset, byte value)
        {
            if (offset < 0)
            {
                if (endIndex + offset < startIndex)
                {
                    return;
                }

                heap[endIndex + offset] = value;
                return;
            }
            if (startIndex + offset >= endIndex) //TODO: this looks wrong, check with lali
            {
                heap[startIndex + offset] = value;
            }
        }

        /// <summary>
        /// Adds a single byte to the end of the stored data.
        /// This expands the internal buffer by 0x1000 bytes if the heap is full
        /// </summary>
        /// <param name="value"></param>
        public void appendByte(byte value)
        {
            if (endIndex + 1 < heapSize())
            {
                heap[endIndex] = value;
                endIndex += 1;
                return;
            }

            var currentData = getActualDataAsSpan();

            heap = new byte[((int)Math.Ceiling((currentData.Length + 1) / (double)blockSize) + 1) * blockSize];
            currentData.CopyTo(heap);
            heap[currentData.Length] = value;
            startIndex = 0;
            endIndex = currentData.Length + 1;
        }

        /// <summary>
        /// Concatenates a buffer to the end of the stored data.
        /// If the new data exceeds the size of the heap then the internal heap
        /// gets expanded by the integer multiples of 0x1000 bytes
        /// </summary>
        /// <param name="newData"></param>
        public void append(ReadOnlySpan<byte> newData)
        {
            if (this.endIndex + newData.Length < this.heapSize())
            {
                newData.CopyTo(this.heap.AsSpan().Slice(this.endIndex));
                this.endIndex += newData.Length;
                return;
            }

            var currentData = this.getActualDataAsSpan();

            this.heap = new byte[
              ((int)Math.Ceiling((currentData.Length + newData.Length) / (double)blockSize) + 1) * blockSize
            ];
            currentData.CopyTo(this.heap);
            newData.CopyTo(this.heap.AsSpan().Slice(currentData.Length));

            this.startIndex = 0;
            this.endIndex = currentData.Length + newData.Length;
        }

        /// <summary>
        /// Returns a slice of data from the internal data.
        /// offset and a limit can be specified:
        /// offset determines the starting position, limit specifies the number of bytes read.
        ///
        /// Watch out! The returned slice of Buffer points to the same Buffer in memory!
        /// This is intentional for performance reasons.
        /// </summary>
        /// <param name="offset"></param>
        /// <param name="limit"></param>
        /// <returns></returns>
        public ReadOnlyMemory<byte> read(int offset, int limit)
        {
            if (offset < 0 || limit < 1)
            {
                return ReadOnlyMemory<byte>.Empty;
            }

            if (offset + limit < this.size())
            {
                return this.heap.AsMemory(this.startIndex + offset, limit);
            }

            return this.getActualDataAsMemory(offset);
        }


        /// <summary>
        /// Reads a single byte from the stored data
        /// </summary>
        /// <param name="offset"></param>
        /// <returns></returns>
        public byte readByte(int offset = 0)
        {
            return this.heap[this.startIndex + offset];
        }

        /// <summary>
        /// Does hard delete
        ///
        /// Removes data from the start of the internal buffer(heap)
        /// by copying bytes to lower indices making sure the
        /// startIndex goes back to 0 afterwards
        /// </summary>
        /// <param name="numberOfBytes"></param>
        public void flushStart(int numberOfBytes)
        {
            numberOfBytes = Math.Clamp(numberOfBytes, 0, this.heapSize());
            if (numberOfBytes > 0)
            {
                if (numberOfBytes < this.heapSize())
                {
                    this.heap.AsSpan(startIndex + numberOfBytes).CopyTo(this.heap);
                }

                this.endIndex -= this.startIndex + numberOfBytes;
                this.startIndex = 0;
            }
        }

        /// <summary>
        /// Does hard delete
        /// Removes data from the end of the internal buffer (heap)
        /// by moving the endIndex back
        /// </summary>
        /// <param name="numberOfBytes"></param>
        public void flushEnd(int numberOfBytes)
        {
            var clampedNumberOfBytes = Math.Clamp(numberOfBytes, 0, this.heapSize());
            if (clampedNumberOfBytes > 0)
            {
                this.endIndex -= clampedNumberOfBytes;
            }
        }

        /// <summary>
        /// Does soft delete
        ///
        /// Removes data from the start of the internal buffer(heap)
        /// by moving the startIndex forward
        /// When the heap gets empty it also resets the indices as a cleanup
        /// </summary>
        /// <param name="numberOfBytes"></param>
        public void dropStart(int numberOfBytes)
        {
            if (numberOfBytes <= 0)
            {
                return;
            }

            this.startIndex += numberOfBytes;
            if (this.startIndex >= this.endIndex)
            {
                this.clear();
            }
        }
        /// <summary>
        /// Does soft delete
        ///
        /// removes data from the end of the internal buffer(heap)
        /// by moving the endIndex back
        /// When the heap gets empty it also resets the indices as a cleanup
        /// </summary>
        /// <param name="numberOfBytes"></param>
        public void dropEnd(int numberOfBytes)
        {
            if (numberOfBytes <= 0)
            {
                return;
            }

            this.endIndex -= numberOfBytes;
            if (this.startIndex >= this.endIndex)
            {
                this.clear();
            }
        }

        /// <summary>
        /// returns the internal buffer
        /// </summary>
        /// <returns></returns>
        public byte[] getHeap()
        {
            return this.heap;
        }

        public void clear()
        {
            this.startIndex = 0;
            this.endIndex = 0;
        }

        public void saveIndices()
        {
            this.startIndexBackup = this.startIndex;
            this.endIndexBackup = this.endIndex;
        }

        public void restoreIndices()
        {
            this.startIndex = this.startIndexBackup;
            this.endIndex = this.endIndexBackup;
        }
    }
}
