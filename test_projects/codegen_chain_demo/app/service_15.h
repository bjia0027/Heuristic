#pragma once
#include <functional>
#include <vector>

class Service15 {
public:
    Service15();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
