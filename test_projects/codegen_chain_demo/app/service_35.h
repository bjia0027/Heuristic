#pragma once
#include <functional>
#include <vector>

class Service35 {
public:
    Service35();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
