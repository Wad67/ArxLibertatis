using ArxLibertatisEditorIO.Util;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.IO;
using System.Text;

namespace ArxLibertatisEditorIO.RawIO.PK.Implode
{
    //from https://github.com/arx-tools/node-pkware/blob/5e75119e5571972c5524231bf10c91a78a09ea44/src/bin/implode.ts

    public class ImplodeFromLali
    {
        bool verbose = false;
        bool isFirstChunk = true;
        ExpandingBuffer inputBuffer;
        ExpandingBuffer outputBuffer;
        int chunkCounter = 0;
        Compression compressionType = Compression.Unknown;
        DictionarySize dictionarySize = DictionarySize.Unknown;
        int dictionarySizeMask = -1;
        bool streamEnded = false;
        byte[] distCodes = (byte[])Constants.DistCode.Clone();
        byte[] distBits = (byte[])Constants.DistBits.Clone();
        int startIndex = 0;
        bool handledFirstTwoBytes = false;
        int outBits = 0;
        byte[] nChBits = new byte[0x306];
        byte[] nChCodes = new byte[0x306];

        public ImplodeFromLali(Compression compressionType, DictionarySize dictionarySize, int inputBufferSize = 0, int outputBufferSize = 0, bool verbose = false)
        {
            this.compressionType = compressionType;
            this.dictionarySize = dictionarySize;
            this.inputBuffer = new ExpandingBuffer(inputBufferSize);
            this.outputBuffer = new ExpandingBuffer(outputBufferSize);
            this.verbose = verbose;
        }

        //TODO: omg lali what is this function??
        //public object getHandler()
        //{
        //return (object/*Transform*/ dis, byte[] chunk, object /*BufferEncoding*/ encoding, object callback) =>
        //{

        //};
        //}


        public static byte[] DoImplode(byte[] bytes)
        {
            MemoryStream output = new MemoryStream();

            var header = new ImplodeHeader();

            header.literalSize = ImplodeLiteralSize.Fixed;
            header.dictSize = ImplodeDictSize.Size1024;

            using (var sw = new StructWriter(output, Encoding.UTF8, true))
            {
                sw.WriteStruct(header);
            }

            BitStream bits = new BitStream();

            for (int i = 0; i < bytes.Length; i++)
            {
                bits.WriteFixedLiteral(bytes[i]);
            }
            bits.WriteEOS();
            while (bits.ByteReady())
            {
                output.WriteByte(bits.GetByte());
            }
            output.WriteByte(bits.GetBytePadded());

            return output.ToArray();
        }
    }
}
