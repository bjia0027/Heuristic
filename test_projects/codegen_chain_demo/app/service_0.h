#pragma once
#include <functional>
#include <vector>

class Service0 {
public:
    Service0();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
