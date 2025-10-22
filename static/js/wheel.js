document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('wheelCanvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const spinButton = document.getElementById('spinButton');
    const resultBox = document.getElementById('resultBox');
    const resultText = document.getElementById('resultText');

    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = centerX - 10;
    let rotation = 0;
    let isSpinning = false;
    let finalPrize = null;
    let sectors = [];

    // --- Confetti Animation ---
    function fireConfetti() {
        confetti({
            particleCount: 150,
            spread: 90,
            origin: { y: 0.6 }
        });
        
        setTimeout(() => {
             confetti({
                particleCount: 100,
                spread: 120,
                origin: { x: 0.5, y: 0.8 },
                colors: ['#00BFFF', '#FFFFFF', '#A0A0A0']
            });
        }, 300);
    }

    // --- Drawing the Wheel (Function Body Omitted for brevity) ---
    function drawWheel() {
        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.rotate(rotation);
        ctx.translate(-centerX, -centerY);
        
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const totalSegments = prizesData.reduce((sum, p) => sum + p.quantity, 0);
        if (totalSegments === 0) {
            ctx.restore();
            return;
        }

        let startAngle = 0;
        let segmentIndex = 0;

        const colors = ['#2C333F', '#363E4A'];

        if (!isSpinning) {
            sectors = [];
        }

        prizesData.forEach(prize => {
            const angle = 2 * Math.PI * (prize.quantity / totalSegments);
            
            for (let i = 0; i < prize.quantity; i++) {
                const segmentAngle = angle / prize.quantity;
                const segmentEndAngle = startAngle + segmentAngle;

                ctx.beginPath();
                ctx.arc(centerX, centerY, radius, startAngle, segmentEndAngle);
                ctx.lineTo(centerX, centerY);
                ctx.closePath();
                
                ctx.fillStyle = colors[segmentIndex % colors.length];
                ctx.fill();
                
                if (!isSpinning) {
                    sectors.push({
                        start: startAngle,
                        end: segmentEndAngle,
                        prize: prize.amount,
                        mid: startAngle + segmentAngle / 2
                    });
                }

                ctx.save();
                ctx.translate(centerX, centerY);
                ctx.rotate(startAngle + segmentAngle / 2);
                
                ctx.fillStyle = '#E0E0E0';
                ctx.font = 'bold 16px monospace';
                ctx.textAlign = 'right';
                ctx.fillText(`$${prize.amount}`, radius * 0.9, 0);
                
                ctx.restore();

                ctx.strokeStyle = '#FFFFFF';
                ctx.lineWidth = 1;
                ctx.shadowColor = '#00BFFF';
                ctx.shadowBlur = 5;
                ctx.beginPath();
                ctx.moveTo(centerX, centerY);
                ctx.lineTo(centerX + radius * Math.cos(startAngle), centerY + radius * Math.sin(startAngle));
                ctx.stroke();
                
                ctx.shadowBlur = 0;

                startAngle = segmentEndAngle;
                segmentIndex++;
            }
        });

        ctx.beginPath();
        ctx.arc(centerX, centerY, 30, 0, 2 * Math.PI);
        ctx.fillStyle = '#A0A0A0';
        ctx.fill();
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 3;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
        ctx.strokeStyle = '#00BFFF';
        ctx.lineWidth = 4;
        ctx.shadowColor = '#00BFFF';
        ctx.shadowBlur = 10;
        ctx.stroke();
        ctx.shadowBlur = 0;
        
        ctx.restore();
    }


    // --- Spinning Logic (Function Body Omitted for brevity) ---
    function rotateWheel(duration) {
        isSpinning = true;
        spinButton.disabled = true;

        const totalRotations = 5 * Math.PI * 2;
        const targetSector = sectors.find(s => s.prize === finalPrize);
        
        if (!targetSector) {
             console.error("Target prize not found in sectors.");
             isSpinning = false;
             spinButton.disabled = false;
             return;
        }

        let targetRotation = 2 * Math.PI - targetSector.mid + Math.PI * 1.5;
        targetRotation = (targetRotation % (2 * Math.PI));
        const finalRotation = totalRotations + targetRotation;
        
        let startTime = null;

        function animate(timestamp) {
            if (!startTime) startTime = timestamp;
            const elapsed = timestamp - startTime;
            const progress = Math.min(1, elapsed / duration);
            
            const easedProgress = 1 - Math.pow(1 - progress, 3); 
            
            rotation = easedProgress * finalRotation;
            
            drawWheel();

            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                isSpinning = false;
                showResult();
                fireConfetti();
            }
        }

        requestAnimationFrame(animate);
    }

    // --- API and Result Handling ---

    async function handleSpin() {
        if (isSpinning) return;
        spinButton.disabled = true;

        try {
            const response = await fetch('/spin', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();

            if (data.error) {
                resultText.textContent = `Error: ${data.error}`;
                resultBox.classList.remove('hidden');
                return;
            }

            finalPrize = data.prize;
            rotateWheel(6000);
        } catch (error) {
            console.error('Spin failed:', error);
            resultText.textContent = 'A network error occurred. Try again.';
            resultBox.classList.remove('hidden');
        }
    }

    function showResult() {
        const formatter = new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        });
        
        // FIX: The prize amount is an integer. Formatting it with currency style fixes the 1000->10 issue.
        const formattedPrize = formatter.format(finalPrize);
        
        // REMOVED BOLD MARKDOWN (**)
        resultText.innerHTML = `CONGRATULATIONS!<br>You Won ${formattedPrize}!`;
        resultBox.classList.remove('hidden');
    }

    // --- Initialization ---
    if (canvas) {
        drawWheel();
        spinButton.addEventListener('click', handleSpin);
    }
});
